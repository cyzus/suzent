from __future__ import annotations

import asyncio
import time

from suzent.logger import get_logger
from suzent.sync.service import GitHubSyncService

logger = get_logger(__name__)


class SyncAutomationRunner:
    def __init__(self, service: GitHubSyncService | None = None) -> None:
        self.service = service or GitHubSyncService()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._next_sync_at: dict[str, float] = {}

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
            sleep_seconds = 4 * 3600
            try:
                profiles = [
                    profile
                    for profile in self.service.list_profiles()
                    if profile.auto_sync_enabled
                ]
                now = time.monotonic()
                enabled_ids = {profile.id for profile in profiles}
                for profile_id in list(self._next_sync_at):
                    if profile_id not in enabled_ids:
                        self._next_sync_at.pop(profile_id, None)

                for profile in profiles:
                    due_at = self._next_sync_at.setdefault(profile.id, now)
                    if due_at > now:
                        continue
                    try:
                        await self.service.auto_sync(profile.id)
                    except Exception as exc:
                        logger.warning("Automatic GitHub sync failed: {}", exc)
                    finally:
                        self._next_sync_at[profile.id] = (
                            time.monotonic() + max(1, profile.interval_hours) * 3600
                        )

                if profiles:
                    next_due = min(
                        self._next_sync_at.get(profile.id, now) for profile in profiles
                    )
                    sleep_seconds = max(1, next_due - time.monotonic())
            except Exception as exc:
                logger.warning("Sync automation tick failed: {}", exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_seconds)
            except asyncio.TimeoutError:
                pass
