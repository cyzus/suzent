"""
Global registry tracking active streaming sessions.

Extracted from streaming.py so that other modules (heartbeat, scheduler)
can check for active streams without importing the full streaming module.
"""

import asyncio
from typing import Dict, Optional


class StreamControl:
    """Holds cooperative cancellation state for an active stream."""

    __slots__ = ("cancel_event", "completed_event", "reason")

    def __init__(self):
        self.cancel_event = asyncio.Event()
        self.completed_event = asyncio.Event()  # Set when post-processing finishes
        self.reason = "Stream stopped by user"


# Global registry of active streams: chat_id -> StreamControl
stream_controls: Dict[str, StreamControl] = {}

# Cache policy-decided approvals for suspended streams so resume payloads
# can merge explicit user decisions with backend auto-decisions.
pending_auto_approvals: Dict[str, Dict[str, bool]] = {}


def stop_stream(chat_id: str, reason: str = "Stream stopped by user") -> bool:
    """Request to stop an active stream."""
    control = stream_controls.get(chat_id)
    if not control:
        return False
    control.reason = reason
    control.cancel_event.set()
    return True


def merge_pending_auto_approvals(chat_id: str, approvals: Dict[str, bool]) -> None:
    """Merge auto-approval decisions for a chat into the pending cache."""
    if not chat_id or not approvals:
        return
    existing = pending_auto_approvals.get(chat_id, {})
    existing.update(approvals)
    pending_auto_approvals[chat_id] = existing


def pop_pending_auto_approvals(chat_id: str) -> Dict[str, bool]:
    """Return and clear cached auto-approvals for a chat."""
    if not chat_id:
        return {}
    return pending_auto_approvals.pop(chat_id, {})


# ---------------------------------------------------------------------------
# Active stream queues
# Maps chat_id → out_queue for the currently-active /chat stream, so that
# background tasks (e.g. sub-agents) can inject custom SSE events into the
# live stream that the user is watching.
# ---------------------------------------------------------------------------

active_stream_queues: Dict[str, asyncio.Queue] = {}


def register_active_stream(chat_id: str, queue: asyncio.Queue) -> None:
    """Register the active out_queue for a chat stream."""
    if chat_id:
        active_stream_queues[chat_id] = queue


def unregister_active_stream(chat_id: str) -> None:
    """Remove the active out_queue when the stream ends."""
    active_stream_queues.pop(chat_id, None)


def get_active_stream_queue(chat_id: str) -> Optional[asyncio.Queue]:
    """Return the active out_queue for a chat, or None if not streaming."""
    return active_stream_queues.get(chat_id)


# ---------------------------------------------------------------------------
# Background stream queues
# Maps chat_id → asyncio.Queue of raw SSE chunks from background executors.
# A None sentinel in the queue signals end-of-stream.
# ---------------------------------------------------------------------------

background_queues: Dict[str, asyncio.Queue] = {}


def register_background_stream(chat_id: str) -> asyncio.Queue:
    """Create and register a background SSE queue for a chat. Returns the queue."""
    existing = background_queues.get(chat_id)
    if existing is not None:
        # Signal any live subscriber on the old queue to terminate gracefully
        # so it doesn't hang on a dead queue for up to 60 seconds.
        try:
            existing.put_nowait(None)
        except asyncio.QueueFull:
            pass
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    background_queues[chat_id] = q
    return q


def unregister_background_stream(chat_id: str) -> None:
    """Remove the background queue for a chat (signals no active stream)."""
    background_queues.pop(chat_id, None)


def get_background_queue(chat_id: str) -> Optional[asyncio.Queue]:
    """Return the active background queue for a chat, or None if not streaming."""
    return background_queues.get(chat_id)


def is_background_streaming(chat_id: str) -> bool:
    """Return True if a background stream is currently active for this chat."""
    return chat_id in background_queues
