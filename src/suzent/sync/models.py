from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SyncProfile(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    repo_path: str
    branch: str = "main"
    remote: str = "origin"
    device_id: str = Field(default_factory=lambda: uuid4().hex)
    auto_sync_enabled: bool = True
    interval_hours: int = Field(default=4, ge=1)
    auto_resolve_enabled: bool = True
    last_revision: str | None = None
    last_sync_at: datetime | None = None


class SyncManifest(BaseModel):
    app: str = "suzent"
    format_version: int = 1
    revision_id: str
    created_at: datetime = Field(default_factory=utc_now)
    source_device: str
    included_paths: list[str]
    content_hashes: dict[str, str]


class SyncFileChange(BaseModel):
    path: str
    category: Literal["config", "skills", "memory", "sync", "other"]
    change_type: Literal["added", "modified", "deleted"]
    risk: Literal["low", "medium", "high"] = "low"
    direction: Literal["outgoing", "incoming"] = "outgoing"


class SyncPlan(BaseModel):
    operation: Literal["push", "pull", "auto"]
    files: list[SyncFileChange] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    destructive: bool = False
    requires_confirmation: bool = False
    warnings: list[str] = Field(default_factory=list)


class DevicePresence(BaseModel):
    device_id: str
    device_name: str
    status: Literal["online", "offline", "stale"] = "online"
    last_seen: datetime = Field(default_factory=utc_now)
    app_version: str | None = None
    last_sync_revision: str | None = None


class SyncConflict(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    conflicting_paths: list[str]
    local_hashes: dict[str, str] = Field(default_factory=dict)
    remote_hashes: dict[str, str] = Field(default_factory=dict)
    base_hashes: dict[str, str] = Field(default_factory=dict)
    status: Literal["detected", "resolving", "manual", "resolved"] = "detected"
    resolution_mode: Literal["agent", "manual", "none"] = "none"


class ConflictResolutionResult(BaseModel):
    chosen_merge: dict[str, str] = Field(default_factory=dict)
    explanation: str = ""
    changed_paths: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["preview", "applied", "failed", "cancelled"] = "preview"


class GitHubIdentity(BaseModel):
    username: str
    email: str | None = None
    source: Literal["git"] = "git"
