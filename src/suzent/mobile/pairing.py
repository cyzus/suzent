"""Operator-approved pairing, separate from Node and peer-agent grants."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClientPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chat_ids: list[str] = Field(default_factory=list)
    all_chats: bool = False
    create_chats: bool = False
    send: bool = False
    stop: bool = False

    def permits_chat(self, chat_id: str) -> bool:
        return self.all_chats or chat_id in self.chat_ids


class ClientGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    display_name: str
    platform: Literal["ios", "android"]
    approved_at: float
    permissions: ClientPermissions


class PairingError(ValueError):
    pass


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class PairingStore:
    """Persist only credential hashes; invitations never survive a restart.

    All transitions hold one lock so concurrent scans and approvals cannot mint
    multiple grants. Disk writes finish before a new credential is returned.
    """

    TTL = 300
    MAX_PENDING = 32

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._pending: dict[str, dict] = {}
        self._grants: dict[str, ClientGrant] = {}
        if path.exists():
            self._grants = {
                digest: ClientGrant.model_validate(record)
                for digest, record in json.loads(path.read_text()).items()
            }

    def _save(self, grants: dict[str, ClientGrant]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(
                    {key: grant.model_dump() for key, grant in grants.items()}, output
                )
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self._grants = grants

    def _prune(self) -> None:
        now = time.time()
        self._pending = {
            key: value
            for key, value in self._pending.items()
            if value["expires_at"] > now
        }

    def invite(self) -> dict:
        with self._lock:
            self._prune()
            if len(self._pending) >= self.MAX_PENDING:
                raise PairingError("Too many pending invitations")
            invitation = secrets.token_urlsafe(32)
            pairing_id = secrets.token_hex(16)
            expires_at = time.time() + self.TTL
            self._pending[pairing_id] = {
                "invitation_hash": _digest(invitation),
                "expires_at": expires_at,
                "status": "invited",
            }
            return {
                "pairing_id": pairing_id,
                "invitation": invitation,
                "expires_at": expires_at,
            }

    def claim(
        self,
        pairing_id: str,
        invitation: str,
        display_name: str,
        platform: Literal["ios", "android"],
    ) -> dict:
        if not display_name.strip() or len(display_name) > 100:
            raise PairingError("Invalid device name")
        if platform not in ("ios", "android"):
            raise PairingError("Invalid platform")
        with self._lock:
            self._prune()
            pending = self._pending.get(pairing_id)
            if (
                not pending
                or pending["status"] != "invited"
                or not secrets.compare_digest(
                    pending["invitation_hash"], _digest(invitation)
                )
            ):
                raise PairingError("Invitation unavailable")
            pickup = secrets.token_urlsafe(32)
            pending.update(
                status="pending",
                display_name=display_name.strip(),
                platform=platform,
                pickup_hash=_digest(pickup),
            )
            del pending["invitation_hash"]
            return {"pickup_secret": pickup, "expires_at": pending["expires_at"]}

    def pending(self) -> list[dict]:
        with self._lock:
            self._prune()
            return [
                {
                    "pairing_id": key,
                    **{
                        field: value[field]
                        for field in ("display_name", "platform", "expires_at")
                    },
                }
                for key, value in self._pending.items()
                if value["status"] == "pending"
            ]

    def decide(self, pairing_id: str, permissions: ClientPermissions | None) -> None:
        with self._lock:
            self._prune()
            pending = self._pending.get(pairing_id)
            if not pending or pending["status"] != "pending":
                raise PairingError("Pairing unavailable")
            pending["status"] = "approved" if permissions is not None else "denied"
            if permissions is not None:
                pending["permissions"] = permissions.model_copy(deep=True)

    def collect(self, pairing_id: str, pickup_secret: str) -> dict:
        with self._lock:
            self._prune()
            pending = self._pending.get(pairing_id)
            if not pending or not secrets.compare_digest(
                pending.get("pickup_hash", ""), _digest(pickup_secret)
            ):
                raise PairingError("Pairing unavailable")
            if pending["status"] != "approved":
                return {"status": pending["status"]}
            token = secrets.token_urlsafe(32)
            grant = ClientGrant(
                device_id=secrets.token_hex(16),
                display_name=pending["display_name"],
                platform=pending["platform"],
                approved_at=time.time(),
                permissions=pending["permissions"],
            )
            self._save({**self._grants, _digest(token): grant})
            del self._pending[pairing_id]
            return {"status": "approved", "token": token, "device": grant.model_dump()}

    def verify(self, token: str) -> ClientGrant | None:
        with self._lock:
            grant = self._grants.get(_digest(token)) if token else None
            return grant.model_copy(deep=True) if grant else None

    def devices(self) -> list[dict]:
        with self._lock:
            return [grant.model_dump() for grant in self._grants.values()]

    def add_chat(self, device_id: str, chat_id: str) -> bool:
        with self._lock:
            for digest, grant in self._grants.items():
                if grant.device_id != device_id:
                    continue
                if grant.permissions.all_chats or chat_id in grant.permissions.chat_ids:
                    return True
                permissions = grant.permissions.model_copy(
                    update={"chat_ids": [*grant.permissions.chat_ids, chat_id]}
                )
                self._save(
                    {
                        **self._grants,
                        digest: grant.model_copy(update={"permissions": permissions}),
                    }
                )
                return True
            return False

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            remaining = {
                key: grant
                for key, grant in self._grants.items()
                if grant.device_id != device_id
            }
            if len(remaining) == len(self._grants):
                return False
            self._save(remaining)
            return True
