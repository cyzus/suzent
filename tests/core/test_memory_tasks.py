import asyncio

import pytest

from suzent.core import memory_tasks


async def test_memory_tasks_serialize_and_keep_status_until_queue_drains(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(memory_tasks, "emit_bus_event", events.append)
    release = asyncio.Event()
    entered = asyncio.Event()
    order: list[int] = []

    async def run(index: int) -> None:
        async with memory_tasks.memory_task("chat"):
            order.append(index)
            if index == 1:
                entered.set()
                await release.wait()

    first = asyncio.create_task(run(1))
    await entered.wait()
    second = asyncio.create_task(run(2))
    await asyncio.sleep(0)
    assert order == [1]
    assert memory_tasks.memory_task_snapshot() == ["chat"]
    release.set()
    await asyncio.gather(first, second)
    assert order == [1, 2]
    assert [event["active"] for event in events] == [True, True, False]
    assert memory_tasks.memory_task_snapshot() == []
    assert not memory_tasks._locks


async def test_memory_timeout_clears_status(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(memory_tasks, "emit_bus_event", events.append)
    monkeypatch.setattr(memory_tasks, "MEMORY_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(TimeoutError):
        async with memory_tasks.memory_task("chat"):
            await asyncio.Event().wait()
    assert events[-1]["active"] is False
    assert memory_tasks.memory_task_snapshot() == []


async def test_cancelling_queued_memory_task_preserves_running_status(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(memory_tasks, "emit_bus_event", events.append)
    async with memory_tasks.memory_task("chat"):

        async def queued() -> None:
            async with memory_tasks.memory_task("chat"):
                pytest.fail("queued task must not run")

        task = asyncio.create_task(queued())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert memory_tasks.memory_task_snapshot() == ["chat"]
        assert all(event["active"] for event in events)
    assert memory_tasks.memory_task_snapshot() == []
