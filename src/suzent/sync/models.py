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
    encrypted_secret_sync_enabled: bool = False
    secret_sync_available: bool = False
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


class DevicePresence(BaseModel):
    device_id: str
    device_name: str
    status: Literal["online", "offline", "stale"] = "online"
    last_seen: datetime = Field(default_factory=utc_now)
    app_version: str | None = None
    last_sync_revision: str | None = None


class DeviceTrust(BaseModel):
    device_id: str
    public_key: str
    approval_state: Literal["pending", "approved", "revoked"] = "pending"
    verified_identity: dict[str, str] = Field(default_factory=dict)


class ShibbolethKdfParams(BaseModel):
    algorithm: str = "pbkdf2-sha256"
    iterations: int = 600_000
    salt: str


class MnemonicKdfParams(BaseModel):
    algorithm: str = "scrypt"
    salt: str
    n: int = 1 << 17
    r: int = 8
    p: int = 1


class DeviceRegistration(BaseModel):
    device_id: str
    device_name: str
    registered_at: datetime = Field(default_factory=utc_now)
    mnemonic_version: int = 1


class EncryptedSecretBundle(BaseModel):
    provider: str
    key_name: str
    ciphertext: str
    nonce: str
    key_version: int = 1
    wrapped_data_keys: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)


class SecretBundlesFile(BaseModel):
    format_version: int = 1
    kdf: ShibbolethKdfParams | MnemonicKdfParams
    bundles: list[EncryptedSecretBundle] = Field(default_factory=list)
    # format_version 2 fields
    mnemonic_version: int = 1
    mnemonic_fingerprint: str | None = None
    rotated_by: str | None = None
    rotated_at: datetime | None = None
    devices: list[DeviceRegistration] = Field(default_factory=list)


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
