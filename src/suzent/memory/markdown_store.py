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
from typing import List, Optional

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

    async def write_memory_file(self, content: str) -> None:
        """
        Write/update the MEMORY.md file.

        Args:
            content: Full content to write (replaces existing)
        """
        async with self._write_lock:
            header = "# Long-term Memory\n\n"
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            footer = f"\n\n---\n*Last updated: {timestamp}*\n"

            self.memory_file_path.write_text(
                header + content + footer, encoding="utf-8"
            )

        logger.info("Updated MEMORY.md")

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
