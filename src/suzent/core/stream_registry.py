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
  {"event": "goal_tasks_changed", "project_id": "...", "chat_id": "..."}
  {"event": "snapshot",       "streams": ["chat-id-1", ...]}   # sent on connect
"""

import asyncio
import contextvars
import time
from typing import Any, Dict, Optional, Set

from suzent.core.stream_replay import StreamReplay


class StreamControl:
    """Holds cooperative cancellation state for an active stream."""

    __slots__ = (
        "run_id",
        "cancel_event",
        "completed_event",
        "reason",
        "inject",
        "import_citations",
        "_injected",
        "_durable",
    )

    def __init__(self):
        # The run this control cancels, as the registry named it when the run
        # claimed the chat. A stop names its run, and a control for a different
        # one must refuse it rather than cancel a turn nobody asked to stop.
        self.run_id: str | None = None
        self.cancel_event = asyncio.Event()
        self.completed_event = asyncio.Event()  # Set when post-processing finishes
        self.reason = "Stream stopped by user"
        # Set by streaming.py for as long as a pydantic-ai run is in flight:
        # ``inject(content) -> enqueue_id | None`` hands a message to the *running*
        # turn instead of making the caller wait for it to end. A sub-agent result
        # arriving mid-turn is the motivating case -- the parent is busy, not
        # broken, so blocking on it (and eventually timing out) loses the result.
        self.inject = None
        # Set alongside `inject`: adopts citation sources into the live run's
        # CitationManager. A run imports sources once at setup, so a message
        # injected later would carry citation markers that resolve to nothing.
        self.import_citations = None
        # enqueue_id -> Event, set once the run has actually drained that message
        # into its history. An enqueue only promises delivery while the run lives;
        # confirmation is what lets a caller ack rather than hope.
        self._injected: Dict[str, asyncio.Event] = {}
        # enqueue_id -> Event, set once a delivered message has been written to
        # the database. Delivery alone is an in-memory fact: acking a durable
        # inbox row on it would lose the message outright if the process died
        # before the run checkpointed.
        self._durable: Dict[str, asyncio.Event] = {}

    def injection_delivered(self, enqueue_id: str) -> asyncio.Event:
        """Return the event that fires once `enqueue_id` lands in the run."""
        event = self._injected.get(enqueue_id)
        if event is None:
            event = asyncio.Event()
            self._injected[enqueue_id] = event
        return event

    def injection_persisted(self, enqueue_id: str) -> asyncio.Event:
        """Return the event that fires once `enqueue_id` is safely on disk."""
        event = self._durable.get(enqueue_id)
        if event is None:
            event = asyncio.Event()
            self._durable[enqueue_id] = event
        return event

    def mark_injected(self, enqueue_id: str) -> None:
        """Record that the live run absorbed a previously injected message."""
        self.injection_delivered(enqueue_id).set()

    def mark_history_persisted(self) -> None:
        """Record that the run's history -- with everything delivered into it so
        far -- has been written to the database."""
        for enqueue_id, delivered in self._injected.items():
            if delivered.is_set():
                self.injection_persisted(enqueue_id).set()


# Global registry of active streams: chat_id -> StreamControl
stream_controls: Dict[str, StreamControl] = {}

# Per-chat lock serializing background turns (heartbeat, wakeup, cron) so only
# one process_background_turn runs at a time for a given chat_id.
_background_turn_locks: Dict[str, asyncio.Lock] = {}


# Cap on retained per-chat background-turn locks. Without a bound, one Lock per
# chat_id that ever ran a background turn (heartbeat/cron/wakeup) accumulates for
# the process lifetime. We prune idle locks once the dict grows past this — locks
# held or awaited by a live turn are left alone.
_MAX_BACKGROUND_TURN_LOCKS = 512


def _lock_in_use(lock: asyncio.Lock) -> bool:
    """True if a lock is held or has queued waiters.

    Checking ``locked()`` alone is not enough: ``asyncio.Lock.release()``
    momentarily makes ``locked()`` False during the handoff to a waiter, before
    that waiter resumes and re-marks the lock held. Pruning in that window would
    drop a lock with a queued background turn, letting a second lock be minted
    for the same chat and breaking the serialization guarantee. So also treat a
    lock with waiters as in-use.
    """
    if lock.locked():
        return True
    waiters = getattr(lock, "_waiters", None)
    return bool(waiters)


def _prune_idle_background_turn_locks() -> None:
    """Drop idle background-turn locks when the registry grows too large."""
    if len(_background_turn_locks) <= _MAX_BACKGROUND_TURN_LOCKS:
        return
    idle = [
        cid for cid, lock in _background_turn_locks.items() if not _lock_in_use(lock)
    ]
    for cid in idle:
        _background_turn_locks.pop(cid, None)


def get_background_turn_lock(chat_id: str) -> asyncio.Lock:
    """Return (creating if needed) the serialization lock for background turns on chat_id."""
    if chat_id not in _background_turn_locks:
        _prune_idle_background_turn_locks()
        _background_turn_locks[chat_id] = asyncio.Lock()
    return _background_turn_locks[chat_id]


# Cache policy-decided approvals for suspended streams so resume payloads
# can merge explicit user decisions with backend auto-decisions.
pending_auto_approvals: Dict[str, Dict[str, bool]] = {}
_pending_auto_approval_times: Dict[str, float] = {}
_MAX_PENDING_AUTO_APPROVAL_CHATS = 512
_PENDING_AUTO_APPROVAL_TTL_SECONDS = 60 * 60


def _prune_pending_auto_approvals(now: float) -> None:
    expired = [
        chat_id
        for chat_id, updated_at in _pending_auto_approval_times.items()
        if now - updated_at > _PENDING_AUTO_APPROVAL_TTL_SECONDS
    ]
    for chat_id in expired:
        pending_auto_approvals.pop(chat_id, None)
        _pending_auto_approval_times.pop(chat_id, None)

    overflow = len(pending_auto_approvals) - _MAX_PENDING_AUTO_APPROVAL_CHATS
    if overflow <= 0:
        return
    oldest = sorted(_pending_auto_approval_times, key=_pending_auto_approval_times.get)
    for chat_id in oldest[:overflow]:
        pending_auto_approvals.pop(chat_id, None)
        _pending_auto_approval_times.pop(chat_id, None)


def stop_stream(
    chat_id: str,
    reason: str = "Stream stopped by user",
    expect_run: str | None = None,
) -> bool:
    """Request to stop an active stream.

    `expect_run` is the run the caller means to stop. The control a chat holds
    is not always the run the caller matched against: a steer registers the
    replacement run's replay before the replacement turn takes the chat's
    control, so for that moment the control still belongs to the turn being
    replaced. Cancelling it would report success for a stop that left the turn
    the user actually stopped running.
    """
    control = stream_controls.get(chat_id)
    if not control:
        return False
    if expect_run is not None and control.run_id != expect_run:
        return False
    control.reason = reason
    control.cancel_event.set()
    return True


def defer_stop_to_pending_run(chat_id: str, reason: str) -> bool:
    """Leave a stop on the current replay for the run that has yet to start.

    The turn takes it when it claims the chat, so the stop still ends in the
    STREAM_END the client is waiting for instead of being silently dropped.
    """
    queue = background_queues.get(chat_id)
    if queue is None or not queue.producer_active:
        return False
    queue.replay.stop_requested = reason
    return True


# The replay of the run the current task is producing. A producer that looks
# its replay up by chat_id can find someone else's: a steer registers the
# replacement run's replay while the turn it replaces may still be starting up,
# so for that moment the chat's current replay is not this producer's own.
current_run_replay: contextvars.ContextVar[Optional[StreamReplay]] = (
    contextvars.ContextVar("current_run_replay", default=None)
)


def bind_producer_replay(replay: Optional[StreamReplay]) -> None:
    """Declare, from inside a producer task, which run it is producing.

    Each producer runs in its own task and therefore its own context copy, so
    this is scoped to that run and everything it awaits.
    """
    current_run_replay.set(replay)


def claim_stream_control(chat_id: str, control: StreamControl) -> None:
    """Install `control` as the chat's, and hand it any stop already accepted.

    The run is the one this producer declared it was producing -- not whichever
    replay the chat currently holds, which during a steer is already the
    replacement's. A producer that declared nothing leaves the control unnamed,
    and an unnamed control refuses every stop that names a run; that is the
    safe direction, since those turns have no replay for a stop to have been
    matched against in the first place.
    """
    stream_controls[chat_id] = control
    replay = current_run_replay.get()
    if replay is None:
        return
    control.run_id = replay.run_id
    replay.producer_started = True
    pending = replay.stop_requested
    if pending:
        replay.stop_requested = None
        control.reason = pending
        control.cancel_event.set()


def merge_pending_auto_approvals(chat_id: str, approvals: Dict[str, bool]) -> None:
    """Merge auto-approval decisions for a chat into the pending cache."""
    if not chat_id or not approvals:
        return
    now = time.monotonic()
    _prune_pending_auto_approvals(now)
    existing = pending_auto_approvals.get(chat_id, {})
    existing.update(approvals)
    pending_auto_approvals[chat_id] = existing
    _pending_auto_approval_times[chat_id] = now
    _prune_pending_auto_approvals(now)


def pop_pending_auto_approvals(chat_id: str) -> Dict[str, bool]:
    """Return and clear cached auto-approvals for a chat."""
    if not chat_id:
        return {}
    _pending_auto_approval_times.pop(chat_id, None)
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
            q.get_nowait()
            q.put_nowait(None)
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

    def __init__(self, chat_id: str, maxsize: int = 4096):
        self.chat_id = chat_id
        self.replay = StreamReplay(maxsize)
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        # Cleared when the None sentinel is put so is_background_streaming()
        # returns False as soon as the producer finishes, even if a late
        # /chat/live client hasn't drained the queue yet.
        self.producer_active: bool = True
        # Set when the None sentinel is put; lets waiters avoid spinning.
        self.done_event: asyncio.Event = asyncio.Event()

    # --- write side ---

    async def put(self, item) -> None:
        self.put_nowait(item)

    def put_nowait(self, item) -> None:
        if item is None and not self.producer_active:
            return
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "chunk":
            item = item[1]
        self.replay.append(item)
        if item is None:
            self.producer_active = False
            self.done_event.set()
        if self._q.full():
            self._q.get_nowait()
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
_MAX_COMPLETED_STREAMS = 64
_COMPLETED_STREAM_TTL = 300.0


def _prune_completed_streams() -> None:
    now = time.monotonic()
    completed = sorted(
        (
            (cid, q.replay.closed_at)
            for cid, q in background_queues.items()
            if q.replay.closed_at is not None
            and (q.replay.persistence is None or q.replay.persistence.done())
        ),
        key=lambda entry: entry[1],
    )
    for index, (cid, closed_at) in enumerate(completed):
        if (
            now - closed_at > _COMPLETED_STREAM_TTL
            or index < len(completed) - _MAX_COMPLETED_STREAMS
        ):
            background_queues.pop(cid, None)


def register_background_stream(chat_id: str) -> _BusStreamQueue:
    """Create and register a background SSE queue for a chat. Returns the queue."""
    _prune_completed_streams()
    existing = background_queues.get(chat_id)
    if existing is not None:
        # Signal any live subscriber on the old queue to terminate gracefully
        # so it doesn't hang on a dead queue for up to 60 seconds.
        try:
            existing.replay.superseded = True
            existing.put_nowait(None)
        except asyncio.QueueFull:
            pass
    q = _BusStreamQueue(chat_id)
    background_queues[chat_id] = q
    _emit_to_bus({"event": "stream_started", "chat_id": chat_id})
    return q


def try_register_background_stream(chat_id: str) -> Optional[_BusStreamQueue]:
    """Register a background SSE queue unless a producer is already active."""
    existing = background_queues.get(chat_id)
    if existing is not None and existing.producer_active:
        return None
    return register_background_stream(chat_id)


def unregister_background_stream(
    chat_id: str, queue: Optional[_BusStreamQueue] = None
) -> None:
    """End production, retaining recovery state under the normal replay policy."""
    current = background_queues.get(chat_id)
    if current is None or (queue is not None and current is not queue):
        return
    current.put_nowait(None)
    # Persistence can outlive the producer. Registry pruning owns eviction so
    # scheduler/social cleanup cannot strand observers during the final save.
    _prune_completed_streams()


def get_background_queue(chat_id: str) -> Optional[_BusStreamQueue]:
    """Return the active background queue for a chat, or None if not streaming."""
    _prune_completed_streams()
    return background_queues.get(chat_id)


def is_background_streaming(chat_id: str) -> bool:
    """Return True if a background stream producer is still active for this chat.

    Returns False as soon as the producer puts the None sentinel, even if the
    queue still exists for late-arriving /chat/live consumers to drain.
    """
    q = background_queues.get(chat_id)
    return q is not None and q.producer_active


async def push_custom_event(chat_id: str, event_name: str, data: Any) -> None:
    """Push a custom SSE event to the active or background queue for chat_id.

    Prefers the live /chat stream; falls back to background_queues for
    heartbeat/social/subagent contexts.
    """
    try:
        from suzent.streaming import _encode_custom

        chunk = _encode_custom(event_name, data)
        q = active_stream_queues.get(chat_id) or background_queues.get(chat_id)
        if q is not None:
            try:
                q.put_nowait(("chunk", chunk))
            except asyncio.QueueFull:
                pass
    except Exception:
        pass
