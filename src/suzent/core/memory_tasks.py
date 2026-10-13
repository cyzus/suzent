"""Bounded, serialized memory work with reconnectable UI status."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from suzent.core.stream_registry import emit_bus_event

MEMORY_TIMEOUT_SECONDS = 60.0
_pending: dict[str, int] = {}
_locks: dict[str, asyncio.Lock] = {}


def memory_task_snapshot() -> list[str]:
    return list(_pending)


@asynccontextmanager
async def memory_task(chat_id: str) -> AsyncIterator[None]:
    _pending[chat_id] = _pending.get(chat_id, 0) + 1
    lock = _locks.setdefault(chat_id, asyncio.Lock())
    emit_bus_event({"event": "memory_processing", "chat_id": chat_id, "active": True})
    try:
        async with lock:
            async with asyncio.timeout(MEMORY_TIMEOUT_SECONDS):
                yield
    finally:
        _pending[chat_id] -= 1
        if not _pending[chat_id]:
            del _pending[chat_id]
            del _locks[chat_id]
            emit_bus_event(
                {"event": "memory_processing", "chat_id": chat_id, "active": False}
            )
