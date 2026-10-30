"""
Markdown-based memory store.

Provides human-readable, file-based memory persistence using plain markdown files
in the /shared/memory/ workspace. This creates a transparent memory layer where:
- The agent can directly read/write memory files via ReadFileTool/WriteFileTool
- The memory system automatically writes extracted facts to the same files
- LanceDB serves as the search index over this markdown content

Two-tier structure (inspired by OpenClaw):
- Daily logs: YYYY-MM-DD.md (append-only, timestamped facts per conversation)
- MEMORY.md: a curated map of vault pages, one pointer per line (see memory_map.py)
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)


def _read_text(path: Path) -> str:
    """Read a memory file as UTF-8, tolerating stray non-UTF-8 bytes.

    Memory files are edited by the agent, hand-edited by the user, and appended to
    by the system; any one of them can slip in a non-UTF-8 byte (e.g. a Latin-1 `é`
    pasted into a daily log). A strict `read_text(encoding="utf-8")` then raises a
    UnicodeDecodeError that wedges the whole reader (the dream loop, the indexer,
    recall). Decoding with `errors="replace"` keeps the rest of the content readable
    instead of losing the file — the offending byte becomes U+FFFD.
    """
    return path.read_text(encoding="utf-8", errors="replace")


class MarkdownMemoryStore:
    """
    Manages markdown memory files in the shared workspace.

    Files are stored at {base_dir}/ which maps to /shared/memory/ from the
    agent's perspective. Both the agent (via file tools) and the memory system
    (via this class) operate on the same physical files.
    """

    def __init__(self, base_dir: str, notebook_dir: Optional[str] = None):
        """
        Initialize the markdown memory store.

        Args:
            base_dir: Physical path to the operational memory directory
                      (e.g., .suzent/sandbox/shared/memory/)
            notebook_dir: Physical path to the always-on notebook vault
                      (defaults to CONFIG.notebook_dir, e.g. ~/.suzent/notebook).
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Daily logs live in a dedicated subdirectory so the root stays clean
        self.archive_dir = self.base_dir / "archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        # The notebook vault (durable wiki) — always-on, separate from operational memory.
        from suzent.config import CONFIG

        self.notebook_dir = Path(notebook_dir or CONFIG.notebook_dir)
        self.notebook_dir.mkdir(parents=True, exist_ok=True)
        self.notebook_state_dir = self.notebook_dir / ".state"
        self.notebook_state_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = asyncio.Lock()
        logger.info(
            f"MarkdownMemoryStore initialized at {self.base_dir} (notebook: {self.notebook_dir})"
        )

    # --- Notebook vault: pages, log.md, watermark ---

    _NAV_FILES = {"schema.md", "index.md", "log.md", "SCHEMA.md", "INDEX.md", "LOG.md"}

    def list_notebook_pages(self) -> List[Path]:
        """All content pages in the vault (recursive *.md), excluding nav files + .state/."""
        pages = []
        for p in self.notebook_dir.rglob("*.md"):
            if ".state" in p.parts:
                continue
            if p.parent == self.notebook_dir and p.name in self._NAV_FILES:
                continue
            pages.append(p)
        return sorted(pages)

    def notebook_rel(self, path: Path) -> str:
        """Root-relative POSIX path of a vault file (the index `source_file` key)."""
        return path.relative_to(self.notebook_dir).as_posix()

    @property
    def notebook_log_path(self) -> Path:
        return self.notebook_dir / "log.md"

    def read_notebook_log(self) -> str:
        p = self.notebook_log_path
        return _read_text(p) if p.exists() else ""

    async def append_notebook_log(self, entry: str) -> None:
        async with self._write_lock:
            with open(self.notebook_log_path, "a", encoding="utf-8") as f:
                f.write(entry.rstrip() + "\n")

    def read_watermark(self) -> Optional[str]:
        """Latest `watermark=YYYY-MM-DD` token in log.md, or None if absent."""
        matches = re.findall(r"watermark=(\d{4}-\d{2}-\d{2})", self.read_notebook_log())
        return matches[-1] if matches else None

    async def write_watermark_entry(self, run_date: str, watermark: str) -> None:
        """Append the authoritative consolidation entry (runner-owned; plan NEW-1/C5)."""
        await self.append_notebook_log(
            f"\n## [{run_date}] ingest | daily logs  watermark={watermark}"
        )

    def read_last_lint_date(self) -> Optional[str]:
        """Date of the most recent `## [YYYY-MM-DD] lint` entry in log.md, or None.

        The lint phase has no watermark (it audits the whole vault); its cadence gate
        keys off how long ago the last lint ran, recorded by these log entries.
        """
        matches = re.findall(
            r"##\s*\[(\d{4}-\d{2}-\d{2})\]\s*lint\b", self.read_notebook_log()
        )
        return matches[-1] if matches else None

    async def write_lint_entry(self, run_date: str, summary: str = "") -> None:
        """Append the runner-owned lint event (mirrors write_watermark_entry)."""
        line = f"\n## [{run_date}] lint"
        if summary:
            line += f"\n{summary.strip()}"
        await self.append_notebook_log(line)

    # --- Recall log (usage signal for the MEMORY.md map lint) ---

    @property
    def recall_log_path(self) -> Path:
        return self.notebook_state_dir / "recall_log.jsonl"

    def append_recall(
        self, snippet: str, source_type: str = "", source_file: str = ""
    ) -> None:
        """Best-effort append of one retrieval event (never raises)."""
        try:
            line = json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "snippet": (snippet or "")[:160],
                    "source_type": source_type,
                    "source_file": source_file,
                }
            )
            with open(self.recall_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def read_recalls(self) -> List[dict]:
        out: List[dict] = []
        p = self.recall_log_path
        if not p.exists():
            return out
        for line in _read_text(p).splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return out

    # --- Tombstones (user-deleted facts the indexer must skip) ---

    @property
    def tombstones_path(self) -> Path:
        return self.notebook_state_dir / "tombstones.jsonl"

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").lower().split())

    async def append_tombstone(self, content: str) -> None:
        async with self._write_lock:
            with open(self.tombstones_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"content": self._normalize(content)}) + "\n")

    def read_tombstones(self) -> set:
        out: set = set()
        p = self.tombstones_path
        if not p.exists():
            return out
        for line in _read_text(p).splitlines():
            line = line.strip()
            if line:
                try:
                    out.add(json.loads(line).get("content", ""))
                except Exception:
                    continue
        return out

    def is_tombstoned(self, content: str, tombstones: Optional[set] = None) -> bool:
        ts = tombstones if tombstones is not None else self.read_tombstones()
        return self._normalize(content) in ts

    def recalled_files(self, days: int = 60) -> set:
        """Vault files retrieval returned in the last *days* days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return {
            r["source_file"]
            for r in self.read_recalls()
            if r.get("source_file") and str(r.get("ts", "")) >= cutoff
        }

    # --- Rejected claims (the user said they are wrong; never captured again) ---

    @property
    def rejected_path(self) -> Path:
        return self.notebook_state_dir / "rejected.jsonl"

    async def append_rejected(
        self, content: str, date: str, correction_id: str = ""
    ) -> None:
        """Record a claim the user rejected.

        A tombstone hides one index row; a rejection stops the claim coming back:
        capture drops matching candidates, the dream treats the list as exclusions and
        lint flags matches in every always-injected file.
        """
        async with self._write_lock:
            with open(self.rejected_path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "content": content.strip(),
                            "date": date,
                            "correction_id": correction_id,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def read_rejected(self) -> List[str]:
        """Rejected claim texts, oldest first, de-duplicated."""
        return [r["content"] for r in self._read_jsonl(self.rejected_path, "content")]

    def is_rejected(self, content: str, rejected: Optional[List[str]] = None) -> bool:
        """Whether *content* restates a rejected claim (normalized, either direction)."""
        body = self._normalize(content)
        if not body:
            return False
        for claim in rejected if rejected is not None else self.read_rejected():
            key = self._normalize(claim)
            if key and (key in body or body in key):
                return True
        return False

    def _read_jsonl(self, path: Path, key: str) -> List[dict]:
        """Records of a sidecar that carry *key*, de-duplicated on it."""
        if not path.exists():
            return []
        out: List[dict] = []
        seen: set = set()
        for line in _read_text(path).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not isinstance(rec, dict) or not rec.get(key):
                continue
            norm = self._normalize(str(rec[key]))
            if norm in seen:
                continue
            seen.add(norm)
            out.append(rec)
        return out

    # --- Review queue (questions the dream leaves for the user) ---

    @property
    def review_queue_path(self) -> Path:
        return self.notebook_state_dir / "review_queue.md"

    def read_review_queue(self) -> List[str]:
        """Open questions, one per `- ` line. The dream writes; the user answers."""
        p = self.review_queue_path
        if not p.exists():
            return []
        return [
            ln.strip()[2:].strip()
            for ln in _read_text(p).splitlines()
            if ln.strip().startswith("- ") and ln.strip()[2:].strip()
        ]

    # --- Dream op log (agent hand-off to log.md) ---

    @property
    def dream_ops_path(self) -> Path:
        return self.notebook_state_dir / "dream_ops.md"

    async def flush_dream_ops(self) -> int:
        """Move the operations the dream recorded into log.md; returns how many.

        The agent may not write log.md (the runner owns the watermark there), so it
        records each create, update, retire and skip in this file and the runner
        appends them under the run's entry.
        """
        p = self.dream_ops_path
        if not p.exists():
            return 0
        body = _read_text(p).strip()
        if not body:
            return 0
        await self.append_notebook_log(body)
        p.write_text("", encoding="utf-8")
        return sum(1 for ln in body.splitlines() if ln.lstrip().startswith("- "))

    # --- Capture drops (what a gate turned away, for review) ---

    @property
    def capture_dropped_path(self) -> Path:
        return self.notebook_state_dir / "capture_dropped.jsonl"

    def append_capture_dropped(self, record: dict) -> None:
        """Best-effort append of one batch's gate drops (never raises)."""
        try:
            with open(self.capture_dropped_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write capture drop log: {e}")

    # --- Superseded facts (dream hand-off to the runner) ---

    @property
    def superseded_path(self) -> Path:
        return self.notebook_state_dir / "superseded.txt"

    def read_superseded(self) -> List[str]:
        """Fact lines the dream folded into the vault and wants out of the index.

        The dream only ever appends here. Turning these into tombstones and
        reindexing the affected logs is the runner's job, so that index mutation
        stays out of the agent's hands and the daily logs stay append-only.
        """
        p = self.superseded_path
        if not p.exists():
            return []
        out: List[str] = []
        seen: set = set()
        for line in _read_text(p).splitlines():
            line = line.strip().lstrip("-").strip()
            if not line:
                continue
            key = self._normalize(line)
            if key in seen:
                continue
            seen.add(key)
            out.append(line)
        return out

    def clear_superseded(self) -> None:
        """Truncate the hand-off file once its lines are tombstoned (never raises)."""
        try:
            if self.superseded_path.exists():
                self.superseded_path.write_text("", encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to clear superseded file: {e}")

    # --- Confirmations (write path hand-off to the dream) ---

    @property
    def confirmations_path(self) -> Path:
        return self.notebook_state_dir / "confirmations.jsonl"

    async def append_confirmation(
        self, content: str, matched: str, date: str, chat_id: str = ""
    ) -> None:
        """Record that a claim already on record was stated again.

        The line the user just said is not appended to the daily log — it is word-for-
        word something durably recorded already, so the only new information is that
        it recurred, and that is what this file holds. The dream folds these into the
        vault's `(confirmed Nx, last YYYY-MM-DD)` markers.
        """
        async with self._write_lock:
            with open(self.confirmations_path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "content": content,
                            "matched": matched,
                            "date": date,
                            "chat_id": chat_id,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def read_confirmations(self) -> List[dict]:
        """Pending confirmations, oldest first. Malformed lines are skipped."""
        p = self.confirmations_path
        if not p.exists():
            return []
        out: List[dict] = []
        for line in _read_text(p).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict) and rec.get("content"):
                out.append(rec)
        return out

    def summarize_confirmations(self, limit: int = 40) -> List[dict]:
        """Pending confirmations collapsed to one row per claim, most-repeated first.

        `[{"content", "count", "last"}]` — the shape the dream prompt needs to bump a
        marker without reading the raw file.
        """
        grouped: Dict[str, dict] = {}
        for rec in self.read_confirmations():
            key = self._normalize(rec.get("content", ""))
            if not key:
                continue
            row = grouped.setdefault(
                key, {"content": rec["content"], "count": 0, "last": ""}
            )
            row["count"] += 1
            date = str(rec.get("date") or "")
            if date > row["last"]:
                row["last"] = date
        rows = sorted(grouped.values(), key=lambda r: (-r["count"], r["content"]))
        return rows[:limit]

    def clear_confirmations(
        self,
        consumed: Optional[int] = None,
        folded: Optional[List[str]] = None,
    ) -> None:
        """Drop the confirmations the dream has folded in (never raises).

        Two things have to be true of what is dropped, and each guards a different way
        of losing evidence this sidecar exists to keep.

        *consumed* is how many lines the file held when the prompt was built. Anything
        after that arrived while the dream ran and the agent never saw it, so the line
        count bounds the damage a truncation could do. Passing None truncates.

        *folded* is the claims that were actually in the prompt. `summarize_confirmations`
        is bounded, so a busy period can leave the file holding more distinct claims
        than the agent was shown; dropping by position alone would then delete the
        unshown ones' evidence permanently. Lines whose claim is not in *folded* are
        kept, wherever they sit. Passing None keeps the old positional behaviour, for
        callers that show everything.
        """
        try:
            p = self.confirmations_path
            if not p.exists():
                return
            if consumed is None and folded is None:
                p.write_text("", encoding="utf-8")
                return
            lines = _read_text(p).splitlines()
            head, tail = lines[: consumed or 0], lines[consumed or 0 :]
            if folded is not None:
                keys = {self._normalize(c) for c in folded if c}
                head = [
                    ln for ln in head if ln.strip() and self._line_claim(ln) not in keys
                ]
            else:
                head = []
            remaining = head + tail
            p.write_text(
                "\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to clear confirmations file: {e}")

    def _line_claim(self, line: str) -> str:
        """The normalized claim a raw sidecar line records, or "" if unreadable."""
        try:
            return self._normalize(json.loads(line).get("content", ""))
        except Exception:
            return ""

    def archive_dates_containing(self, contents: List[str]) -> List[str]:
        """Dates whose daily log holds any of *contents*, oldest first.

        Matching is normalized-substring against the whole log line rather than a
        parse of it: the fact body sits inside the line, and a false positive only
        costs one redundant reindex, which is delete-then-add and therefore
        idempotent. Missing a date, by contrast, would leave the row in the index
        with no mtime change to ever bring the watcher back to it.
        """
        wanted = [self._normalize(c) for c in contents if c and c.strip()]
        if not wanted:
            return []
        dates: set = set()
        for path in sorted(self.archive_dir.glob("????-??-??.md")):
            if not path.is_file():
                continue
            body = self._normalize(_read_text(path))
            if any(w in body for w in wanted):
                dates.add(path.stem)
        return sorted(dates)

    # --- Dream pacing state (durable across restarts) ---

    @property
    def dream_state_path(self) -> Path:
        return self.notebook_state_dir / "dream_state.json"

    def read_dream_failures(self) -> dict:
        """Consecutive no-op counts per batch end date, `{"YYYY-MM-DD": int}`.

        Durable because retry-then-skip is what stops one un-consolidatable batch
        from wedging the backlog forever. Held only in memory, the counter resets
        on every process start, so the skip never fires on a desktop app that
        restarts between attempts and the watermark stops advancing for good.
        """
        p = self.dream_state_path
        if not p.exists():
            return {}
        try:
            data = json.loads(_read_text(p))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        failures = data.get("failures")
        if not isinstance(failures, dict):
            return {}
        return {k: v for k, v in failures.items() if isinstance(v, int)}

    def write_dream_failures(self, failures: dict) -> None:
        """Best-effort persist of the retry counters (never raises)."""
        try:
            self.dream_state_path.write_text(
                json.dumps({"failures": failures}, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to persist dream state: {e}")

    # --- Daily Logs ---

    def _daily_log_path(self, date: str) -> Path:
        """Get path for a daily log file.

        Args:
            date: Date string in YYYY-MM-DD format
        """
        return self.archive_dir / f"{date}.md"

    async def append_daily_log(
        self,
        chat_id: str,
        facts: List[dict],
        date: Optional[str] = None,
    ) -> None:
        """
        Append extracted facts to the daily log file.

        Args:
            chat_id: Chat session identifier
            facts: List of dicts with keys: content, category, tags and, for typed
                capture, evidence (written as a quoted line under the fact)
            date: Date string (defaults to today in UTC)
        """
        if not facts:
            return

        date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._daily_log_path(date)
        now = datetime.now(timezone.utc).strftime("%H:%M")

        # The full id, not a prefix: ids like social-telegram-111/-222 share one.
        lines = [f"\n## {now} — {chat_id}\n"]

        for fact in facts:
            content = fact.get("content", "")
            category = fact.get("category", "general")
            tags = fact.get("tags", [])
            tag_str = f" `{' '.join(tags)}`" if tags else ""

            lines.append(f"- [{category}] {content}{tag_str}")
            evidence = " ".join(str(fact.get("evidence") or "").split())
            if evidence:
                lines.append(f'  > "{evidence[:300]}"')

        entry = "\n".join(lines) + "\n"

        async with self._write_lock:
            # Ensure archive dir exists (safe to call repeatedly)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Create file with header if it doesn't exist
            if not path.exists():
                header = f"# Daily Log - {date}\n"
                path.write_text(header, encoding="utf-8")

            # Append entry
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry)

        logger.debug(f"Appended {len(facts)} facts to daily log {date}")

    async def read_daily_log(self, date: str) -> Optional[str]:
        """
        Read a daily log file.

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            File content as string, or None if file doesn't exist
        """
        path = self._daily_log_path(date)
        if not path.exists():
            return None
        return _read_text(path)

    def find_fact_origin(self, filename: str, content: str) -> Optional[dict]:
        """Where a daily-log fact was captured: `{"date", "time", "chat_prefix"}`.

        Each capture is appended under a `## HH:MM — <chat id prefix>` heading, so
        the nearest heading above the fact names the conversation it came from.
        """
        path = self.archive_dir / filename
        wanted = self._normalize(content)
        if not wanted or not path.exists():
            return None
        heading: Optional[re.Match] = None
        for line in _read_text(path).splitlines():
            if m := re.match(r"^##\s+(\d{2}:\d{2})\s+—\s+(\S+)\s*$", line):
                heading = m
            elif (
                heading
                and line.lstrip().startswith("- [")
                and (wanted in self._normalize(line))
            ):
                return {
                    "date": path.stem,
                    "time": heading.group(1),
                    "chat_prefix": heading.group(2),
                }
        return None

    def find_chat_facts(
        self,
        chat_id: str,
        since: str,
        limit: int = 50,
        include_legacy: bool = False,
    ) -> list[dict[str, Any]]:
        """Facts captured from *chat_id* in daily logs dated *since* or later, newest first.

        The inverse of :meth:`find_fact_origin`: entries are matched by the chat id
        in their `## HH:MM — <chat id>` heading. Older logs wrote only the first
        eight characters; those count only with *include_legacy*, which the caller
        sets when no other chat shares that prefix.
        """
        owners = {chat_id}
        if include_legacy:
            owners.add(chat_id[:8])
        facts: list[dict[str, Any]] = []
        if not self.archive_dir.exists():
            return facts
        logs = sorted(
            (
                path
                for path in self.archive_dir.glob("*.md")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem) and path.stem >= since
            ),
            reverse=True,
        )
        for path in logs:
            entries: list[dict[str, Any]] = []
            time: Optional[str] = None
            for line in _read_text(path).splitlines():
                if m := re.match(r"^##\s+(\d{2}:\d{2})\s+—\s+(\S+)\s*$", line):
                    time = m.group(1) if m.group(2) in owners else None
                elif time and (
                    m := re.match(r"^- \[([^\]]*)\]\s+(.*?)(?:\s+`([^`]*)`)?\s*$", line)
                ):
                    tags = (m.group(3) or "").split()
                    kind = next(
                        (tag[5:] for tag in tags if tag.startswith("kind:")), None
                    )
                    entries.append(
                        {
                            "date": path.stem,
                            "time": time,
                            "category": m.group(1),
                            "kind": kind,
                            "content": m.group(2),
                            "revision": "revision" in tags,
                        }
                    )
            facts.extend(reversed(entries))
            if len(facts) >= limit:
                break
        return facts[:limit]

    async def get_recent_logs(self, days: int = 2) -> str:
        """
        Read recent daily logs (today and yesterday by default).

        Args:
            days: Number of days to look back

        Returns:
            Combined content of recent logs
        """
        content_parts = []
        today = datetime.now(timezone.utc).date()

        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            log = await self.read_daily_log(date)
            if log:
                content_parts.append(log)

        return "\n\n---\n\n".join(content_parts) if content_parts else ""

    async def list_daily_logs(self) -> List[str]:
        """List available daily log dates, newest first.

        Returns:
            List of date strings (YYYY-MM-DD)
        """
        logs = [p.stem for p in self.archive_dir.glob("????-??-??.md") if p.is_file()]
        logs.sort(reverse=True)
        return logs

    # --- Long-term Memory (MEMORY.md) ---

    @property
    def memory_file_path(self) -> Path:
        """Path to the memory map."""
        return self.base_dir / "MEMORY.md"

    def core_memory_revision(self, chat_id: Optional[str] = None) -> tuple:
        """Cheap fingerprint of every file that feeds the core-memory prompt.

        A handful of ``stat`` calls, so it is safe to consult on every model request.
        Callers cache the rendered core-memory section against this value and
        rebuild only when it changes, which is what keeps an edit to
        ``persona.md`` from waiting on the next agent rebuild to take effect.
        """
        paths = [
            self._block_path("persona"),
            self._block_path("user"),
            self.memory_file_path,
            self.review_queue_path,
        ]
        if chat_id:
            try:
                paths.append(self._context_path(chat_id))
            except Exception:
                # Project lookup can fail for a chat with no project yet; the
                # remaining files still give a usable revision.
                pass

        fingerprint = []
        for path in paths:
            try:
                stat = path.stat()
                fingerprint.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                fingerprint.append((str(path), None, None))
        return tuple(fingerprint)

    async def write_memory_map(self, content: str) -> None:
        """Replace MEMORY.md with *content*, whole.

        The file is one curated map with no generated zone: the dream and the user
        both edit it, and lint checks every line the same way.
        """
        async with self._write_lock:
            self.memory_file_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        logger.info("Updated MEMORY.md map")

    async def write_memory_map_if_missing(self, draft: str) -> bool:
        """Write *draft* only when MEMORY.md does not exist or is empty.

        An existing file is somebody's work, even when it is not a map yet; turning
        it into one goes through the cleanup drafts and the user's review.
        """
        async with self._write_lock:
            path = self.memory_file_path
            if path.exists() and _read_text(path).strip():
                return False
            path.write_text(draft.rstrip() + "\n", encoding="utf-8")
        logger.info("Wrote a draft MEMORY.md map")
        return True

    async def read_memory_file(self) -> Optional[str]:
        """
        Read the MEMORY.md file.

        Returns:
            File content as string, or None if file doesn't exist
        """
        if not self.memory_file_path.exists():
            return None
        return _read_text(self.memory_file_path)

    # --- Core Memory Blocks (persona.md, user.md, etc.) ---

    def _block_path(self, label: str) -> Path:
        """Get path for a named block file (e.g., persona.md)."""
        return self.base_dir / f"{label}.md"

    def _context_path(self, chat_id: str) -> Path:
        """Get path for the project-scoped context.md.

        Context is shared across all chats in the same project, so the file
        lives at ``projects/{slug}/context.md`` rather than in a per-chat dir.
        """
        from suzent.database import get_database

        return get_database().get_project_dir(chat_id) / "context.md"

    def _project_context_path(self, project_id: str) -> Path:
        """Get the context.md path for a project without requiring a chat."""
        from suzent.config import CONFIG
        from suzent.database import get_database

        project = get_database().get_project(project_id)
        if project is None:
            raise ValueError(f"Unknown project: {project_id}")
        return Path(CONFIG.sandbox_data_path) / "projects" / project.slug / "context.md"

    async def read_block(self, label: str) -> Optional[str]:
        """Read a named core memory block file (e.g., persona.md).

        Args:
            label: Block name without extension (e.g., 'persona', 'user')

        Returns:
            File content, or None if file does not exist
        """
        path = self._block_path(label)
        if not path.exists():
            return None
        return _read_text(path)

    async def write_block(self, label: str, content: str) -> None:
        """Write a named core memory block file.

        Args:
            label: Block name without extension (e.g., 'persona', 'user')
            content: Full content to write
        """
        async with self._write_lock:
            path = self._block_path(label)
            path.write_text(content, encoding="utf-8")
        logger.debug(f"Updated block file: {label}.md")

    async def read_session_context(self, chat_id: str) -> Optional[str]:
        """Read the project-scoped context.md for a chat.

        Context is shared across all chats in the same project.
        """
        path = self._context_path(chat_id)
        if not path.exists():
            return None
        return _read_text(path)

    async def write_session_context(self, chat_id: str, content: str) -> None:
        """Write the project-scoped context.md for a chat.

        Context is shared across all chats in the same project.
        """
        async with self._write_lock:
            path = self._context_path(chat_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        logger.debug(f"Updated project context for chat {chat_id[:8]}")

    async def read_project_context(self, project_id: str) -> Optional[str]:
        """Read a project's context.md directly by project ID."""
        path = self._project_context_path(project_id)
        if not path.exists():
            return None
        return _read_text(path)

    async def write_project_context(self, project_id: str, content: str) -> None:
        """Write a project's context.md directly by project ID."""
        async with self._write_lock:
            path = self._project_context_path(project_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        logger.debug(f"Updated project context for project {project_id}")
