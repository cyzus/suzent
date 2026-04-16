"""
Global registry tracking active streaming sessions.

Extracted from streaming.py so that other modules (heartbeat, scheduler)
can check for active streams without importing the full streaming module.

Event Bus
---------
All background streams (heartbeat, cron/scheduler, social, subagents) emit their
SSE chunks through a single multiplexed bus: register with `register_bus_subscriber`
to receive every chunk from every background stream, tagged with its chat_id.

Bus event shapes:
  {"event": "stream_started", "chat_id": "..."}
  {"event": "chunk",          "chat_id": "...", "data": "<raw SSE string>"}
  {"event": "stream_ended",   "chat_id": "..."}
  {"event": "snapshot",       "streams": ["chat-id-1", ...]}   # sent on connect
"""

import asyncio
from typing import Dict, Optional, Set


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
# Event bus
# A single persistent fan-out channel: every chunk put on any background
# stream queue is also broadcast here, tagged with the originating chat_id.
# ---------------------------------------------------------------------------

_bus_subscribers: Set[asyncio.Queue] = set()


def register_bus_subscriber() -> asyncio.Queue:
    """Create a new bus subscriber queue and return it."""
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    _bus_subscribers.add(q)
    return q


def unregister_bus_subscriber(q: asyncio.Queue) -> None:
    """Remove a bus subscriber queue."""
    _bus_subscribers.discard(q)


def _emit_to_bus(payload: dict) -> None:
    """Non-blocking broadcast to all bus subscribers. Drops slow consumers."""
    dead: Set[asyncio.Queue] = set()
    for q in _bus_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.add(q)
    _bus_subscribers.difference_update(dead)


def emit_bus_event(payload: dict) -> None:
    """Public helper to broadcast an event-bus payload to all subscribers."""
    if not isinstance(payload, dict):
        return
    _emit_to_bus(payload)


def _fan_chunk_to_bus(chat_id: str, item) -> None:
    """Forward one queue item to the event bus."""
    if item is None:
        _emit_to_bus({"event": "stream_ended", "chat_id": chat_id})
    else:
        _emit_to_bus({"event": "chunk", "chat_id": chat_id, "data": item})


# ---------------------------------------------------------------------------
# Background stream queues
# Maps chat_id → _BusStreamQueue.  A None sentinel signals end-of-stream.
# ---------------------------------------------------------------------------


class _BusStreamQueue:
    """
    Drop-in replacement for asyncio.Queue used by background streams.

    Every item put on this queue is also fanned out to the global event bus
    (tagged with chat_id) so a single /events/stream SSE connection can
    multiplex all background streams without extra per-chat subscriptions.

    Only the methods actually used by the codebase are implemented; everything
    else delegates to the inner asyncio.Queue.
    """

    def __init__(self, chat_id: str, maxsize: int = 2000):
        self.chat_id = chat_id
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    # --- write side ---

    async def put(self, item) -> None:
        await self._q.put(item)
        _fan_chunk_to_bus(self.chat_id, item)

    def put_nowait(self, item) -> None:
        self._q.put_nowait(item)
        _fan_chunk_to_bus(self.chat_id, item)

    # --- read side ---

    async def get(self):
        return await self._q.get()

    def get_nowait(self):
        return self._q.get_nowait()

    def empty(self) -> bool:
        return self._q.empty()

    def qsize(self) -> int:
        return self._q.qsize()


background_queues: Dict[str, _BusStreamQueue] = {}


def register_background_stream(chat_id: str) -> _BusStreamQueue:
    """Create and register a background SSE queue for a chat. Returns the queue."""
    existing = background_queues.get(chat_id)
    if existing is not None:
        # Signal any live subscriber on the old queue to terminate gracefully
        # so it doesn't hang on a dead queue for up to 60 seconds.
        try:
            existing.put_nowait(None)
        except asyncio.QueueFull:
            pass
    q = _BusStreamQueue(chat_id)
    background_queues[chat_id] = q
    _emit_to_bus({"event": "stream_started", "chat_id": chat_id})
    return q


def unregister_background_stream(chat_id: str) -> None:
    """Remove the background queue for a chat (signals no active stream)."""
    background_queues.pop(chat_id, None)
    # stream_ended is already emitted by the None sentinel put_nowait in _BusStreamQueue


def get_background_queue(chat_id: str) -> Optional[_BusStreamQueue]:
    """Return the active background queue for a chat, or None if not streaming."""
    return background_queues.get(chat_id)


def is_background_streaming(chat_id: str) -> bool:
    """Return True if a background stream is currently active for this chat."""
    return chat_id in background_queues
