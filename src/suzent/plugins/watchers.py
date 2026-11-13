"""Runs the watchers that loaded plugins register.

A watcher polls an outside service, such as a mailbox, and reports anything
new to the Mailbox with ``ctx.emit_event``. The runner only sees watchers of
plugins that are loaded, so turning a plugin off stops its watchers.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from typing import Callable, Optional

from suzent.logger import get_logger
from suzent.plugins.context import PluginWatcher

logger = get_logger(__name__)

WatcherList = Callable[[], list[tuple[str, PluginWatcher]]]


def _loaded_watchers() -> list[tuple[str, PluginWatcher]]:
    from suzent.plugins import get_plugin_manager

    return get_plugin_manager().watchers()


class PluginWatcherRunner:
    """Calls each loaded plugin's watchers when they are due, one run at a time each."""

    def __init__(
        self,
        tick_seconds: float = 30.0,
        watchers: WatcherList = _loaded_watchers,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tick = tick_seconds
        self._watchers = watchers
        self._clock = clock
        self._next_run: dict[tuple[str, str], float] = {}
        self._checks: dict[tuple[str, str], asyncio.Task] = {}
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="plugin_watchers")
            logger.info("Plugin watcher runner started")

    async def stop(self) -> None:
        """Stop scheduling, and cancel and wait for every check still running."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        checks = list(self._checks.values())
        for check in checks:
            check.cancel()
        await asyncio.gather(*checks, return_exceptions=True)
        self._checks.clear()

    async def _run(self) -> None:
        while True:
            try:
                self.run_due()
            except Exception:
                logger.error("Plugin watcher round failed:\n{}", traceback.format_exc())
            await asyncio.sleep(self._tick)

    def run_due(self) -> list[asyncio.Task]:
        """Start every watcher that is due and not already running.

        A running check whose watcher is gone (its plugin was turned off) is
        cancelled.
        """
        now = self._clock()
        current = {(plugin_id, w.name): w for plugin_id, w in self._watchers()}
        for key, check in list(self._checks.items()):
            if key not in current:
                check.cancel()
        started = []
        for key, watcher in current.items():
            if key in self._checks or now < self._next_run.get(key, now):
                continue
            self._next_run[key] = now + watcher.every_seconds
            check = asyncio.create_task(
                self._check(key, watcher), name=f"watch-{key[0]}-{key[1]}"
            )
            self._checks[key] = check
            started.append(check)
        return started

    async def _check(self, key: tuple[str, str], watcher: PluginWatcher) -> None:
        try:
            await asyncio.wait_for(watcher.check(), timeout=watcher.every_seconds)
        except asyncio.CancelledError:
            logger.info("Plugin watcher {}/{} was stopped", key[0], key[1])
        except Exception as exc:
            logger.warning("Plugin watcher {}/{} failed: {}", key[0], key[1], exc)
        finally:
            if self._checks.get(key) is asyncio.current_task():
                del self._checks[key]
