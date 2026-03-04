"""
Agent serialization module for persisting and restoring conversation state.

This module handles:
- Serializing pydantic-ai message history to JSON bytes
- Deserializing message history and restoring it for the next turn
- Legacy v2 (smolagents) format detection and graceful fallback
"""

import json
from typing import Optional, Dict, Any, List

from suzent.logger import get_logger

logger = get_logger(__name__)

# Format version for migration detection
STATE_FORMAT_VERSION = 3


# ─── Public API ────────────────────────────────────────────────────────


def serialize_state(
    messages: list,
    model_id: Optional[str] = None,
    tool_names: Optional[List[str]] = None,
) -> Optional[bytes]:
    """
    Serialize pydantic-ai conversation messages to JSON bytes.

    Args:
        messages: Result of ``response.all_messages()`` from a pydantic-ai run.
        model_id: The model identifier string.
        tool_names: List of tool names that were active.

    Returns:
        JSON-encoded bytes, or None on failure.
    """
    try:
        from pydantic_core import to_jsonable_python

        state = {
            "version": STATE_FORMAT_VERSION,
            "model_id": model_id,
            "tool_names": tool_names or [],
            "message_history": to_jsonable_python(messages),
        }
        serialized_data = json.dumps(state, ensure_ascii=False, default=str).encode(
            "utf-8"
        )
        logger.debug(
            f"Serialized agent state: {len(messages)} messages, {len(serialized_data)} bytes"
        )
        return serialized_data

    except Exception as e:
        logger.error(f"Failed to serialize agent state: {e}")
        return None


def deserialize_state(data: bytes) -> Optional[Dict[str, Any]]:
    """
    Deserialize agent state bytes back to a dict containing message_history.

    Returns:
        Dict with keys:
        - ``message_history``: list of pydantic-ai ModelMessage objects
        - ``version``: int
        - ``model_id``: str | None
        - ``tool_names``: list[str]
        Or None if deserialization fails.
    """
    if not data:
        return None

    # --- Try JSON v3 (pydantic-ai messages) ---
    try:
        raw = json.loads(data.decode("utf-8"))
        if isinstance(raw, dict) and raw.get("version") == STATE_FORMAT_VERSION:
            return _restore_v3(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # --- Try JSON v2 (legacy smolagents steps) ---
    try:
        raw = json.loads(data.decode("utf-8"))
        if isinstance(raw, dict) and raw.get("version") == 2:
            logger.info("Detected legacy v2 state — starting fresh conversation")
            return None  # Cannot meaningfully restore smolagents steps
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # --- Try pickle (very old legacy) ---
    try:
        import pickle

        pickle.loads(data)
        logger.info("Detected legacy pickle state — starting fresh conversation")
        return None
    except Exception:
        pass

    logger.warning("Could not deserialize agent state in any format")
    return None


# ─── Internal helpers ──────────────────────────────────────────────────


def _restore_v3(raw: dict) -> Optional[Dict[str, Any]]:
    """Restore v3 format (pydantic-ai message history)."""
    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter

        history_data = raw.get("message_history")
        if history_data is None:
            return None

        messages = ModelMessagesTypeAdapter.validate_python(history_data)

        logger.debug(f"Restored v3 history: {len(messages)} messages")
        return {
            "version": STATE_FORMAT_VERSION,
            "message_history": messages,
            "model_id": raw.get("model_id"),
            "tool_names": raw.get("tool_names", []),
        }

    except Exception as e:
        logger.warning(f"Failed to restore v3 message history: {e}")
        # Log a snippet of history_data for debugging if it's not too large
        try:
            sample = str(history_data)[:500]
            logger.debug(f"History data sample that failed validation: {sample}")
        except Exception:
            pass
        return None


# ─── Backward-compatible shims ─────────────────────────────────────────
# These are kept for callers that haven't been updated yet.


def serialize_agent(agent) -> Optional[bytes]:
    """Legacy shim: serialize from an agent that has ``_last_messages``."""
    messages = getattr(agent, "_last_messages", None)
    if not messages:
        return None

    model_id = getattr(agent, "_model_id", None)
    tool_names = getattr(agent, "_tool_names", [])
    return serialize_state(messages, model_id=model_id, tool_names=tool_names)


def deserialize_agent(
    agent_data: bytes, config: Dict[str, Any], create_agent_fn=None
) -> None:
    """Legacy shim: returns None — pydantic-ai agents don't need to be
    'restored' since message history is passed at run time.

    Callers should use ``deserialize_state()`` + ``message_history=`` instead.
    """
    return None
