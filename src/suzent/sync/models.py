from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SyncProfile(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    repo_path: str
    branch: str = "main"
    remote: str = "origin"
    auto_sync_enabled: bool = True
    interval_hours: int = Field(default=4, ge=1)
    last_sync_at: datetime | None = None


class SyncFileChange(BaseModel):
    path: str
    category: Literal["config", "skills", "memory", "other"]
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


class GitHubIdentity(BaseModel):
    username: str
    email: str | None = None
    source: Literal["git"] = "git"
