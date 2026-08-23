"""
Markdown-based memory store.

Provides human-readable, file-based memory persistence using plain markdown files
in the /shared/memory/ workspace. This creates a transparent memory layer where:
- The agent can directly read/write memory files via ReadFileTool/WriteFileTool
- The memory system automatically writes extracted facts to the same files
- LanceDB serves as the search index over this markdown content

Two-tier structure (inspired by OpenClaw):
- Daily logs: YYYY-MM-DD.md (append-only, timestamped facts per conversation)
- Long-term memory: MEMORY.md (curated summary of important facts)
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

# MEMORY.md is written by two generators and edited directly by the agent, which the
# core-memory prompt actively tells it to do. Only the region between these markers is
# regenerated; everything after the end marker is preserved verbatim, so a note the
# agent or the user adds is not destroyed by the next consolidation.
MEMORY_GENERATED_START = "<!-- memory:generated - rewritten on consolidation -->"
MEMORY_GENERATED_END = "<!-- /memory:generated - notes below this line are kept -->"

# The footer written by every pre-marker version of write_memory_file. Its presence is
# what identifies an unmarked file as generator-authored and therefore safe to replace.
_LEGACY_FOOTER_RE = re.compile(r"^\*Last updated: .*UTC\*\s*$", re.MULTILINE)


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

    # --- Recall log (usage signal for MEMORY.md promotion) ---

    @property
    def recall_log_path(self) -> Path:
        return self.notebook_state_dir / "recall_log.jsonl"

    def append_recall(self, snippet: str, source_type: str = "") -> None:
        """Best-effort append of one retrieval event (never raises)."""
        try:
            line = json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "snippet": (snippet or "")[:160],
                    "source_type": source_type,
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

    def truncate_recalls(self) -> None:
        try:
            self.recall_log_path.write_text("", encoding="utf-8")
        except Exception:
            pass

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

    def clear_confirmations(self, consumed: Optional[int] = None) -> None:
        """Drop the confirmations the dream has folded in (never raises).

        *consumed* is the number of lines that were in the file when the prompt was
        built. Conversations keep appending here while the dream runs, so truncating
        the whole file would silently discard every confirmation recorded during the
        run — the one thing this sidecar exists to not do. Passing None truncates.
        """
        try:
            p = self.confirmations_path
            if not p.exists():
                return
            if consumed is None:
                p.write_text("", encoding="utf-8")
                return
            remaining = _read_text(p).splitlines()[consumed:]
            p.write_text(
                "\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to clear confirmations file: {e}")

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
            facts: List of dicts with keys: content, category, importance, tags, context
            date: Date string (defaults to today in UTC)
        """
        if not facts:
            return

        date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._daily_log_path(date)
        now = datetime.now(timezone.utc).strftime("%H:%M")

        # Build lean markdown entry (OpenClaw-style: scannable, not verbose)
        lines = [f"\n## {now} — {chat_id[:8]}\n"]

        for fact in facts:
            content = fact.get("content", "")
            category = fact.get("category", "general")
            tags = fact.get("tags", [])
            tag_str = f" `{' '.join(tags)}`" if tags else ""

            lines.append(f"- [{category}] {content}{tag_str}")

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
        """Path to the curated long-term memory file."""
        return self.base_dir / "MEMORY.md"

    def manual_tail(self, existing: str) -> str:
        """Whatever a generator must not touch, taken from the current MEMORY.md.

        Three cases, in order:

        - Marked file: everything after the end marker is the manual zone.
        - Unmarked but generator-authored: nothing to keep. Recognised by the footer
          only this method ever wrote, so the test cannot be fooled by an agent that
          merely reused the heading.
        - Anything else: the whole file. A file we did not write is somebody's work,
          and a blind overwrite is exactly how it used to get lost.
        """
        if MEMORY_GENERATED_END in existing:
            return existing.split(MEMORY_GENERATED_END, 1)[1].strip()
        if not existing.strip():
            return ""
        if _LEGACY_FOOTER_RE.search(existing):
            return ""
        return existing.strip()

    async def write_memory_manual_zone(self, content: str, actor: str) -> None:
        """Replace the human-owned half of MEMORY.md, keeping the generated half.

        This is the fourth writer to this file: a person editing the `facts` block in
        the UI. It used to be a raw whole-file write, which meant a human correction
        either got clobbered by the next consolidation or got copied down into the
        manual zone alongside the generated original.

        Their text lands in the manual zone, where nothing overwrites it, and carries
        an OKF-style `human:` verification stamp — a person's correction is evidence
        of a different quality than anything the extractor produced, and this is the
        record of that. Anything they typed inside the generated zone is dropped: the
        marker says outright that the region is rewritten, and silently preserving it
        would duplicate every fact the next pass regenerates.
        """
        async with self._write_lock:
            path = self.memory_file_path
            existing = path.read_text(encoding="utf-8") if path.exists() else ""

            if MEMORY_GENERATED_START in existing and MEMORY_GENERATED_END in existing:
                head = existing.split(MEMORY_GENERATED_END, 1)[0] + MEMORY_GENERATED_END
            else:
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                head = (
                    f"# Long-term Memory\n_Consolidated {timestamp}._\n\n"
                    f"{MEMORY_GENERATED_START}\n{MEMORY_GENERATED_END}"
                )

            submitted = content
            if MEMORY_GENERATED_END in submitted:
                submitted = submitted.split(MEMORY_GENERATED_END, 1)[1]

            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            body = f"{head}\n\n<!-- verified: {actor} at {stamp} -->\n"
            if submitted.strip():
                body += f"{submitted.strip()}\n"

            path.write_text(body, encoding="utf-8")

        logger.info("Updated MEMORY.md manual zone (%s)", actor)

    async def write_memory_file(self, content: str) -> None:
        """Rewrite the generated zone of MEMORY.md, preserving the manual zone.

        This file has two writers in code and a third in practice: the agent edits it
        with its ordinary file tools because the core-memory prompt invites it to. The
        write used to be an unconditional `write_text`, so whichever generator ran next
        destroyed that work with no merge, no warning, and no way to notice afterwards.

        Args:
            content: the generated section. Everything after the end marker survives.
        """
        async with self._write_lock:
            path = self.memory_file_path
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            tail = self.manual_tail(existing)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            body = (
                f"# Long-term Memory\n"
                f"_Consolidated {timestamp}._\n\n"
                f"{MEMORY_GENERATED_START}\n"
                f"{content.strip()}\n"
                f"{MEMORY_GENERATED_END}\n"
            )
            if tail:
                body += f"\n{tail}\n"

            path.write_text(body, encoding="utf-8")

        logger.info("Updated MEMORY.md (generated zone, %d chars kept)", len(tail))

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
