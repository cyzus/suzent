"""Data models shared by the service CLI, desktop app, and platform adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ServiceProcessState:
    """Process identity persisted by a running Suzent service."""

    instance_id: str
    control_token: str
    pid: int
    process_created_at: float
    started_at: str
    port: int
    version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    """Stable status contract exposed by ``suzent service status``."""

    installed: bool
    autostart: bool
    running: bool
    ready: bool
    pid: int | None = None
    port: int | None = None
    version: str | None = None
    uptime_seconds: float | None = None
    rss_bytes: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
