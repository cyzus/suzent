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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)


class MarkdownMemoryStore:
    """
    Manages markdown memory files in the shared workspace.

    Files are stored at {base_dir}/ which maps to /shared/memory/ from the
    agent's perspective. Both the agent (via file tools) and the memory system
    (via this class) operate on the same physical files.
    """

    def __init__(self, base_dir: str):
        """
        Initialize the markdown memory store.

        Args:
            base_dir: Physical path to the memory directory
                      (e.g., .suzent/sandbox/shared/memory/)
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = asyncio.Lock()
        logger.info(f"MarkdownMemoryStore initialized at {self.base_dir}")

    # --- Daily Logs ---

    def _daily_log_path(self, date: str) -> Path:
        """Get path for a daily log file.

        Args:
            date: Date string in YYYY-MM-DD format
        """
        return self.base_dir / f"{date}.md"

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
        return path.read_text(encoding="utf-8")

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
        """
        List available daily log dates, newest first.

        Returns:
            List of date strings (YYYY-MM-DD)
        """
        logs = []
        for path in self.base_dir.glob("????-??-??.md"):
            logs.append(path.stem)
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
        return self.memory_file_path.read_text(encoding="utf-8")
