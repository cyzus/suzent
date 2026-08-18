import asyncio

from suzent.memory import lifecycle


async def test_concurrent_lazy_initialization_shares_one_task(monkeypatch):
    started = 0
    release = asyncio.Event()

    async def initialize() -> bool:
        nonlocal started
        started += 1
        await release.wait()
        return True

    monkeypatch.setattr(lifecycle, "memory_manager", None)
    monkeypatch.setattr(lifecycle, "_initialization_task", None)
    monkeypatch.setattr(lifecycle, "_initialize_memory_system", initialize)

    first = asyncio.create_task(lifecycle.init_memory_system())
    second = asyncio.create_task(lifecycle.init_memory_system())
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(first, second) == [True, True]
    assert started == 1
