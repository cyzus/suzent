from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from suzent.tools.browsing_tool import BrowserSessionManager
from suzent.tools.social_message_tool import SocialMessageTool


class _DummyChannelManager:
    def __init__(self):
        self.channels = {"telegram": object()}
        self.send_message_called = False

    async def send_message(self, platform, target, message):
        self.send_message_called = True
        return True


@pytest.mark.asyncio
async def test_browser_manager_runs_on_main_loop_when_available(monkeypatch):
    manager = BrowserSessionManager()
    main_loop = object()
    manager._main_loop = main_loop

    async def sample_coro():
        return "ok"

    monkeypatch.setattr(
        "suzent.tools.browsing_tool.asyncio.get_running_loop", lambda: main_loop
    )

    result = await manager._run_on_main_loop(sample_coro())

    assert result == "ok"


@pytest.mark.asyncio
async def test_browser_manager_dispatches_to_main_loop(monkeypatch):
    manager = BrowserSessionManager()
    main_loop = object()
    manager._main_loop = main_loop

    async def sample_coro():
        return "routed"

    dispatched = {}

    def fake_run_coroutine_threadsafe(coro, loop):
        dispatched["loop"] = loop
        dispatched["coro"] = coro
        coro.close()
        future = Future()
        future.set_result("routed")
        return future

    monkeypatch.setattr(
        "suzent.tools.browsing_tool.asyncio.get_running_loop", lambda: object()
    )
    monkeypatch.setattr(
        "suzent.tools.browsing_tool.asyncio.run_coroutine_threadsafe",
        fake_run_coroutine_threadsafe,
    )

    result = await manager._run_on_main_loop(sample_coro())

    assert result == "routed"
    assert dispatched["loop"] is main_loop


@pytest.mark.asyncio
async def test_social_message_uses_threadsafe_dispatch(monkeypatch):
    tool = SocialMessageTool()
    channel_manager = _DummyChannelManager()
    event_loop = object()

    dispatched = {}

    def fake_run_coroutine_threadsafe(coro, loop):
        dispatched["loop"] = loop
        dispatched["coro"] = coro
        coro.close()
        future = Future()
        future.set_result(True)
        return future

    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            channel_manager=channel_manager,
            event_loop=event_loop,
            social_context={"platform": "telegram", "target_id": "user-1"},
        )
    )

    monkeypatch.setattr(
        "suzent.tools.social_message_tool.asyncio.run_coroutine_threadsafe",
        fake_run_coroutine_threadsafe,
    )

    result = tool.forward(ctx, message="hello")

    assert result.success
    assert result.message == "Message sent to telegram:user-1"
    assert dispatched["loop"] is event_loop
    assert channel_manager.send_message_called is False
