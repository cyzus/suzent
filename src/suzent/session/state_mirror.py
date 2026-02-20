"""
Agent state mirror — writes human-readable JSON snapshots to disk.

These snapshots live at .suzent/state/{session_id}.json and serve as
diagnostic/inspection tools. They are internal operational data, not
agent-facing (unlike /shared/memory/ which the agent can read/write).
"""

import json
from pathlib import Path
from typing import Optional

from suzent.config import DATA_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)


class StateMirror:
    """Writes inspectable JSON snapshots of agent state after each turn."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or str(DATA_DIR / "state"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def mirror_state(self, session_id: str, state_bytes: bytes) -> None:
        """
        Write a human-readable JSON snapshot from serialized agent state.

        Args:
            session_id: Chat/session ID
            state_bytes: Raw bytes from serialize_agent()
        """
        if not state_bytes:
            return

        path = self.base_dir / f"{session_id}.json"

        try:
            # Try to parse as JSON (v2 format) — already human-readable
            state = json.loads(state_bytes.decode("utf-8"))
            path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            logger.debug(f"Mirrored agent state to {path}")

        except (json.JSONDecodeError, UnicodeDecodeError):
            # Pickle format — write a placeholder noting it's opaque
            path.write_text(
                json.dumps(
                    {"format": "pickle", "note": "Legacy format, not inspectable"},
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.debug(f"Mirrored pickle placeholder to {path}")

        except Exception as e:
            logger.warning(f"Failed to mirror state for {session_id}: {e}")

    def read_state(self, session_id: str) -> Optional[dict]:
        """Read a mirrored state snapshot."""
        path = self.base_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
