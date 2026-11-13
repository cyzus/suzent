import asyncio

import pytest

from suzent.plugins import PluginContext, PluginManifest
from suzent.plugins.context import PluginWatcher
from suzent.plugins.watchers import PluginWatcherRunner


def _ctx(tmp_path) -> PluginContext:
    return PluginContext(PluginManifest(id="acme", name="Acme"), tmp_path)


def test_watchers_must_be_named_once_and_not_too_frequent(tmp_path):
    ctx = _ctx(tmp_path)

    async def check() -> None:
        return None

    ctx.register_watcher("inbox", check, every_seconds=120)
    with pytest.raises(ValueError):
        ctx.register_watcher("inbox", check, every_seconds=120)
    with pytest.raises(ValueError):
        ctx.register_watcher("fast", check, every_seconds=5)
    assert [w.name for w in ctx.watchers] == ["inbox"]


def test_plugin_state_persists_per_plugin(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.state.set("seen", ["1", "2"])

    assert _ctx(tmp_path).state.get("seen") == ["1", "2"]
    other = PluginContext(PluginManifest(id="other"), tmp_path)
    assert other.state.get("seen", []) == []


@pytest.mark.asyncio
async def test_runner_runs_due_watchers_once_at_a_time():
    calls: list[str] = []
    release = asyncio.Event()
    now = [0.0]

    async def slow() -> None:
        calls.append("slow")
        await release.wait()

    async def failing() -> None:
        calls.append("failing")
        raise RuntimeError("service down")

    watchers = [
        ("acme", PluginWatcher("slow", slow, 120)),
        ("acme", PluginWatcher("failing", failing, 120)),
    ]
    runner = PluginWatcherRunner(watchers=lambda: watchers, clock=lambda: now[0])

    first = runner.run_due()
    await asyncio.sleep(0)
    assert sorted(calls) == ["failing", "slow"]

    # Due again, but "slow" is still running, and "failing" isn't due yet.
    now[0] = 60
    assert runner.run_due() == []
    now[0] = 130
    second = runner.run_due()
    await asyncio.sleep(0)
    assert calls.count("failing") == 2
    assert calls.count("slow") == 1

    release.set()
    await asyncio.gather(*first, *second)
    now[0] = 260
    third = runner.run_due()
    await asyncio.gather(*third)
    assert calls.count("slow") == 2


@pytest.mark.asyncio
async def test_runner_cancels_checks_of_plugins_turned_off_and_on_stop():
    started: list[str] = []
    cancelled: list[str] = []

    def hanging(name: str):
        async def check() -> None:
            started.append(name)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(name)
                raise

        return check

    watchers = [
        ("acme", PluginWatcher("inbox", hanging("acme"), 120)),
        ("other", PluginWatcher("feed", hanging("other"), 120)),
    ]
    runner = PluginWatcherRunner(watchers=lambda: list(watchers), clock=lambda: 0.0)
    runner.run_due()
    await asyncio.sleep(0)
    assert sorted(started) == ["acme", "other"]

    watchers.pop(0)
    runner.run_due()
    await asyncio.sleep(0)
    assert cancelled == ["acme"]

    await runner.stop()
    assert sorted(cancelled) == ["acme", "other"]


@pytest.mark.asyncio
async def test_a_turned_off_plugin_cannot_emit_events(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.active = False

    assert await ctx.emit_event(event_type="message", summary="late") is None
