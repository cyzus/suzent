from __future__ import annotations

import asyncio

from suzent.logger import get_logger
from suzent.sync.service import GitHubSyncService

logger = get_logger(__name__)


class SyncAutomationRunner:
    def __init__(self, service: GitHubSyncService | None = None) -> None:
        self.service = service or GitHubSyncService()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            interval_hours = 4
            try:
                profiles = [
                    profile
                    for profile in self.service.list_profiles()
                    if profile.auto_sync_enabled
                ]
                for profile in profiles:
                    interval_hours = profile.interval_hours
                    try:
                        await self.service.auto_sync(profile.id)
                    except Exception as exc:
                        logger.warning("Automatic GitHub sync failed: {}", exc)
            except Exception as exc:
                logger.warning("Sync automation tick failed: {}", exc)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=max(1, interval_hours) * 3600
                )
            except asyncio.TimeoutError:
                pass
