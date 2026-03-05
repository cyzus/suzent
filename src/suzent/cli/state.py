"""
Local state management for the Suzent CLI.

Handles reading and writing the active session configuration (e.g. current_chat_id)
so that the CLI can maintain persistent conversations.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any

from suzent.config import DATA_DIR


def get_state_file() -> Path:
    """Get the path to the CLI state JSON file."""
    # Ensure parents exist just in case, though DATA_DIR is usually pre-created
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "cli_state.json"


def load_state() -> Dict[str, Any]:
    """Load the current CLI state from disk."""
    state_file = get_state_file()
    if not state_file.exists():
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    """Save the CLI state to disk."""
    state_file = get_state_file()
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_current_chat_id() -> Optional[str]:
    """Get the active chat_id for the CLI session."""
    state = load_state()
    return state.get("current_chat_id")


def set_current_chat_id(chat_id: Optional[str]) -> None:
    """Set the active chat_id for the CLI session."""
    state = load_state()
    if chat_id:
        state["current_chat_id"] = chat_id
    else:
        state.pop("current_chat_id", None)
    save_state(state)
