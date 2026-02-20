"""
JSONL transcript manager.

Writes append-only per-session transcripts to .suzent/transcripts/{session_id}.jsonl.
These are internal operational logs (not agent-facing), accessed via API endpoints.

Each line is a JSON object:
  {"ts": "2026-02-08T14:32:00Z", "role": "user"|"assistant", "content": "...", "actions": [...]}
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from suzent.config import DATA_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)


class TranscriptManager:
    """Manages append-only JSONL transcript files per session."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or str(DATA_DIR / "transcripts"))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def _path(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.jsonl"

    async def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        actions: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Append a single turn to the transcript.

        Args:
            session_id: Chat/session ID
            role: "user" or "assistant"
            content: Message content
            actions: Optional list of tool call dicts
            metadata: Optional extra metadata
        """
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "content": content[:10000],  # Cap at 10k chars
        }
        if actions:
            entry["actions"] = actions
        if metadata:
            entry["meta"] = metadata

        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"

        async with self._get_lock(session_id):
            with open(self._path(session_id), "a", encoding="utf-8") as f:
                f.write(line)

    async def read_transcript(
        self, session_id: str, last_n: Optional[int] = None
    ) -> List[dict]:
        """
        Read transcript entries.

        Args:
            session_id: Chat/session ID
            last_n: If set, return only the last N entries
        """
        path = self._path(session_id)
        if not path.exists():
            return []

        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if last_n is not None:
            return entries[-last_n:]
        return entries

    def get_transcript_path(self, session_id: str) -> Path:
        return self._path(session_id)

    def transcript_exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()
