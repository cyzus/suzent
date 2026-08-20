"""
A2A task lifecycle: the state machine and the in-process task store.

This is the piece the existing Suzent peer flow could not express. That flow is
one-shot — post content, stream a reply, done — so a remote agent had no way to
*pause and ask a question*. A2A models that as the ``input-required`` state, and
resuming it is just another ``message/send`` carrying the same ``taskId``.

Durability note: the conversation itself is persisted by the normal chat store
(a task's ``contextId`` is a Suzent chat id). What lives here is the task
*wrapper* — state, artifacts, and live subscribers — which is deliberately
in-memory and bounded. A task interrupted by ``input-required`` survives as long
as the server does; across a restart the client re-sends and gets a new task,
while the conversation context is still there.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

from suzent.a2a.types import (
    Artifact,
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from suzent.logger import get_logger

logger = get_logger(__name__)

# Bounded so a long-lived server can't accumulate task wrappers without limit.
MAX_TRACKED_TASKS = 512

TaskEvent = TaskStatusUpdateEvent | TaskArtifactUpdateEvent

# Legal transitions. Terminal states appear nowhere on the right-hand side of a
# non-terminal source: once a task settles, it stays settled.
_ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    TaskState.submitted: frozenset(
        {
            TaskState.working,
            TaskState.input_required,
            TaskState.auth_required,
            TaskState.completed,
            TaskState.failed,
            TaskState.canceled,
            TaskState.rejected,
        }
    ),
    TaskState.working: frozenset(
        {
            TaskState.working,
            TaskState.input_required,
            TaskState.auth_required,
            TaskState.completed,
            TaskState.failed,
            TaskState.canceled,
        }
    ),
    # An interrupted task resumes when the client supplies what was asked for.
    TaskState.input_required: frozenset(
        {TaskState.working, TaskState.canceled, TaskState.failed}
    ),
    TaskState.auth_required: frozenset(
        {TaskState.working, TaskState.canceled, TaskState.failed}
    ),
}


class TaskTransitionError(RuntimeError):
    """Raised on an illegal state transition (e.g. reviving a settled task)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id() -> str:
    return uuid.uuid4().hex


class TaskRecord:
    """One task plus its live subscribers.

    Subscribers are per-connection queues rather than a shared one so that a
    slow SSE reader can't starve another, and ``tasks/resubscribe`` can attach
    to a task already in flight.
    """

    def __init__(self, task: Task):
        self.task = task
        self._subscribers: list[asyncio.Queue[TaskEvent | None]] = []

    def subscribe(self) -> asyncio.Queue[TaskEvent | None]:
        queue: asyncio.Queue[TaskEvent | None] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[TaskEvent | None]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def publish(self, event: TaskEvent | None) -> None:
        """Fan an event out to every live subscriber (None closes the stream)."""
        for queue in list(self._subscribers):
            queue.put_nowait(event)


class TaskStore:
    """Process-wide registry of A2A tasks we are executing for remote callers."""

    def __init__(self, max_tasks: int = MAX_TRACKED_TASKS):
        self._tasks: OrderedDict[str, TaskRecord] = OrderedDict()
        self._max_tasks = max_tasks
        self._lock = asyncio.Lock()

    # ─── Lookup ──────────────────────────────────────────────────────

    def get(self, task_id: str) -> Task | None:
        record = self._tasks.get(task_id)
        return record.task if record else None

    def record(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        """Newest first — the order the UI wants for a live task list."""
        return [r.task for r in reversed(self._tasks.values())]

    # ─── Creation ────────────────────────────────────────────────────

    async def create(
        self, *, context_id: str, message: Message, task_id: str | None = None
    ) -> Task:
        """Register a freshly submitted task and evict the oldest settled one."""
        task = Task(
            id=task_id or new_task_id(),
            context_id=context_id,
            status=TaskStatus(state=TaskState.submitted, timestamp=_now_iso()),
            history=[message],
            artifacts=[],
        )
        async with self._lock:
            self._tasks[task.id] = TaskRecord(task)
            self._evict_locked()
        return task

    def _evict_locked(self) -> None:
        """Drop oldest *settled* tasks past the cap; never evict a live one."""
        while len(self._tasks) > self._max_tasks:
            for task_id, record in self._tasks.items():
                if record.task.status.state.is_terminal:
                    del self._tasks[task_id]
                    break
            else:
                # Every tracked task is still live — refuse to evict and let the
                # store grow rather than silently killing work in progress.
                logger.warning(
                    "A2A task store above cap ({}) with no settled task to evict",
                    self._max_tasks,
                )
                return

    # ─── Transitions ─────────────────────────────────────────────────

    async def set_state(
        self,
        task_id: str,
        state: TaskState,
        *,
        message: Message | None = None,
        final: bool | None = None,
    ) -> Task:
        """Move a task to ``state``, notifying subscribers.

        ``final`` marks the stream as closing. It defaults to true for terminal
        states and for interrupted ones — an ``input-required`` task ends the
        current stream and waits for a fresh request carrying its ``taskId``.
        """
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise TaskTransitionError(f"Unknown task '{task_id}'")

            current = record.task.status.state
            if state not in _ALLOWED.get(current, frozenset()):
                raise TaskTransitionError(
                    f"Illegal A2A task transition {current.value} -> {state.value}"
                )

            record.task.status = TaskStatus(
                state=state, message=message, timestamp=_now_iso()
            )
            if message is not None:
                record.task.history = (record.task.history or []) + [message]

            is_final = (
                (state.is_terminal or state.is_interrupted) if final is None else final
            )
            record.publish(
                TaskStatusUpdateEvent(
                    task_id=task_id,
                    context_id=record.task.context_id,
                    status=record.task.status,
                    final=is_final,
                )
            )
            if is_final:
                record.publish(None)
            return record.task

    async def add_artifact(
        self,
        task_id: str,
        artifact: Artifact,
        *,
        append: bool = False,
        last_chunk: bool = False,
    ) -> None:
        """Attach an artifact and stream it to subscribers."""
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise TaskTransitionError(f"Unknown task '{task_id}'")
            record.task.artifacts = (record.task.artifacts or []) + [artifact]
            record.publish(
                TaskArtifactUpdateEvent(
                    task_id=task_id,
                    context_id=record.task.context_id,
                    artifact=artifact,
                    append=append,
                    last_chunk=last_chunk,
                )
            )

    async def append_message(self, task_id: str, message: Message) -> Task:
        """Record an inbound message on an existing task without changing state."""
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise TaskTransitionError(f"Unknown task '{task_id}'")
            record.task.history = (record.task.history or []) + [message]
            return record.task

    async def cancel(self, task_id: str) -> Task:
        """Cooperatively cancel. Already-settled tasks are an error per spec."""
        task = self.get(task_id)
        if task is None:
            raise TaskTransitionError(f"Unknown task '{task_id}'")
        if task.status.state.is_terminal:
            raise TaskTransitionError(
                f"Task '{task_id}' is already {task.status.state.value}"
            )
        return await self.set_state(task_id, TaskState.canceled)


_store: TaskStore | None = None


def get_task_store() -> TaskStore:
    """Return the process-wide task store shared by routes and the executor."""
    global _store
    if _store is None:
        _store = TaskStore()
    return _store
