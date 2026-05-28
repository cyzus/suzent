import asyncio
from dataclasses import dataclass

import pytest

from suzent.sync.automation import SyncAutomationRunner


@dataclass
class FakeProfile:
    id: str
    interval_hours: int
    auto_sync_enabled: bool = True


class FakeService:
    def __init__(self) -> None:
        self.synced: list[str] = []

    def list_profiles(self) -> list[FakeProfile]:
        return [
            FakeProfile(id="slow", interval_hours=24),
            FakeProfile(id="fast", interval_hours=1),
        ]

    async def auto_sync(self, profile_id: str) -> dict:
        self.synced.append(profile_id)
        return {"success": True}


class StopLoop(Exception):
    pass


@pytest.mark.asyncio
async def test_automation_sleeps_until_earliest_profile_due(monkeypatch):
    service = FakeService()
    runner = SyncAutomationRunner(service=service)  # type: ignore[arg-type]
    captured_timeout: list[float] = []

    monkeypatch.setattr("suzent.sync.automation.time.monotonic", lambda: 100.0)

    async def fake_wait_for(awaitable, timeout: float):
        awaitable.close()
        captured_timeout.append(timeout)
        raise StopLoop

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(StopLoop):
        await runner._run()

    assert service.synced == ["slow", "fast"]
    assert captured_timeout == [3600]
