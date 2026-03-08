"""
Per-chat run state tracking for steering and queue management.

Shared across all interfaces (desktop, CLI, social). Tracks active tasks,
who triggered them, and queued messages waiting to be processed.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Dict

from suzent.core.stream_registry import stream_controls


@dataclass
class ChatRunState:
    """Tracks the active run and message queue for a single chat."""

    active_task: Optional[asyncio.Task] = None
    active_sender: Optional[str] = None
    queued_messages: list = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_activity: float = field(default_factory=time.time)


# Global registry: chat_id -> ChatRunState
_chat_states: Dict[str, ChatRunState] = {}


def get_run_state(chat_id: str) -> ChatRunState:
    """Get or create the run state for a chat."""
    if chat_id not in _chat_states:
        _chat_states[chat_id] = ChatRunState()
    else:
        # Update last activity timestamp
        _chat_states[chat_id].last_activity = time.time()
    return _chat_states[chat_id]


def is_running(chat_id: str) -> bool:
    """Check if there's an active run for a chat."""
    state = _chat_states.get(chat_id)
    if not state or not state.active_task:
        return False
    return not state.active_task.done()


async def cancel_and_wait(chat_id: str, timeout: float = 5.0) -> bool:
    """
    Cancel the active stream for a chat and wait for cleanup to complete.

    Returns True if there was an active stream that was cancelled.
    """
    control = stream_controls.get(chat_id)
    if not control:
        return False

    # Signal cancellation
    control.cancel_event.set()

    # Wait for the completed_event (set in streaming.py's finally block)
    if hasattr(control, "completed_event"):
        try:
            await asyncio.wait_for(control.completed_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    return True


def cleanup_stale_states(ttl_seconds: float = 3600) -> int:
    """
    Remove inactive run states older than TTL.

    Args:
        ttl_seconds: Time to live in seconds (default 1 hour)

    Returns:
        Number of states cleaned up
    """
    current_time = time.time()
    stale_chat_ids = []

    for chat_id, state in _chat_states.items():
        # Don't clean up if there's an active task
        if state.active_task and not state.active_task.done():
            continue

        # Check if state is stale
        if current_time - state.last_activity > ttl_seconds:
            stale_chat_ids.append(chat_id)

    # Remove stale states
    for chat_id in stale_chat_ids:
        del _chat_states[chat_id]

    return len(stale_chat_ids)
