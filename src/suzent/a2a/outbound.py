"""
Tracker for tasks *we* have delegated to remote A2A agents.

The remote agent owns the authoritative task state; this is our local view of
it, so the Mesh tab can show what is in flight across a UI reload and so an
``input-required`` question is not lost the moment the sending turn ends.

In-memory and bounded, like the inbound store: a delegated task that outlives a
server restart can still be recovered by asking the remote agent for it with
``tasks/get``, because the task id is what identifies it.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from suzent.a2a.types import Task, TaskState

MAX_TRACKED = 128


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OutboundTaskTracker:
    """Local mirror of delegated task state, keyed by (agent_id, task_id)."""

    def __init__(self, max_tracked: int = MAX_TRACKED):
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max = max_tracked
        self._lock = threading.Lock()

    @staticmethod
    def _key(agent_id: str, task_id: str) -> str:
        return f"{agent_id}:{task_id}"

    def record(
        self, *, agent_id: str, agent_name: str, task: Task, prompt: str = ""
    ) -> dict[str, Any]:
        """Insert or update our view of a delegated task."""
        key = self._key(agent_id, task.id)
        with self._lock:
            previous = self._entries.get(key, {})
            entry = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "task_id": task.id,
                "context_id": task.context_id,
                "state": task.status.state.value,
                "message": task.status.message.text() if task.status.message else "",
                "prompt": prompt or previous.get("prompt", ""),
                "created_at": previous.get("created_at") or _now_iso(),
                "updated_at": _now_iso(),
            }
            self._entries[key] = entry
            self._entries.move_to_end(key)
            self._evict_locked()
            return dict(entry)

    def _evict_locked(self) -> None:
        """Drop the oldest settled entries first; keep live ones visible."""
        while len(self._entries) > self._max:
            for key, entry in self._entries.items():
                if TaskState(entry["state"]).is_terminal:
                    del self._entries[key]
                    break
            else:
                self._entries.popitem(last=False)
                return

    def list_tasks(self) -> list[dict[str, Any]]:
        """Newest first, so the UI shows current work at the top."""
        with self._lock:
            return [dict(entry) for entry in reversed(self._entries.values())]

    def get(self, agent_id: str, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(self._key(agent_id, task_id))
            return dict(entry) if entry else None

    def forget_agent(self, agent_id: str) -> None:
        """Drop every tracked task for an agent the operator removed."""
        with self._lock:
            for key in [
                k for k, v in self._entries.items() if v["agent_id"] == agent_id
            ]:
                del self._entries[key]


_tracker: OutboundTaskTracker | None = None


def get_outbound_tracker() -> OutboundTaskTracker:
    global _tracker
    if _tracker is None:
        _tracker = OutboundTaskTracker()
    return _tracker
