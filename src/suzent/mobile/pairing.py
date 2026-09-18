"""Operator-approved pairing, separate from Node and peer-agent grants."""

from __future__ import annotations

import hashlib
import hmac
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
    approve_tools: bool = False

    def permits_chat(self, chat_id: str) -> bool:
        return self.all_chats or chat_id in self.chat_ids


class ClientGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    display_name: str
    platform: Literal["ios", "android"]
    approved_at: float
    permissions: ClientPermissions
    provisional_until: float | None = None


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
        grants = {
            key: grant
            for key, grant in grants.items()
            if grant.provisional_until is None or grant.provisional_until > time.time()
        }
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

    def invite(
        self, permissions: ClientPermissions | None = None, desktop_name: str = "Suzent"
    ) -> dict:
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
            if permissions is not None:
                self._pending[pairing_id].update(
                    permissions=permissions.model_copy(deep=True),
                    desktop_name=desktop_name,
                    preauthorized=True,
                )
            return {
                "pairing_id": pairing_id,
                "invitation": invitation,
                "expires_at": expires_at,
                **({"approval": "phone"} if permissions is not None else {}),
            }

    def preview(self, pairing_id: str) -> dict:
        """Reveal the immutable scope to a holder of the random invitation ID."""
        with self._lock:
            self._prune()
            pending = self._pending.get(pairing_id)
            if (
                not pending
                or pending["status"] != "invited"
                or not pending.get("preauthorized")
            ):
                raise PairingError("Invitation unavailable")
            return {
                "pairing_id": pairing_id,
                "approval": "phone",
                "desktop_name": pending["desktop_name"],
                "permissions": pending["permissions"].model_dump(),
                "expires_at": pending["expires_at"],
            }

    def cancel(self, pairing_id: str) -> bool:
        with self._lock:
            self._prune()
            return self._pending.pop(pairing_id, None) is not None

    @staticmethod
    def repair_proof(digest: str, pairing_id: str, invitation: str, side: str) -> str:
        message = f"suzent-mobile-repair-v1:{side}:{pairing_id}:{invitation}"
        return hmac.new(
            bytes.fromhex(digest), message.encode(), hashlib.sha256
        ).hexdigest()

    def claim(
        self,
        pairing_id: str,
        invitation: str,
        display_name: str,
        platform: Literal["ios", "android"],
        confirm_permissions: bool = False,
        repair_proof: str | None = None,
        rotate: bool = False,
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
            if pending.get("preauthorized") and not confirm_permissions:
                raise PairingError("Confirm the desktop permissions on the phone")
            previous = next(
                (
                    digest
                    for digest, grant in self._grants.items()
                    if grant.platform == platform
                    and grant.provisional_until is None
                    and repair_proof
                    and secrets.compare_digest(
                        repair_proof,
                        self.repair_proof(digest, pairing_id, invitation, "phone"),
                    )
                ),
                None,
            )
            server_proof = None
            if previous:
                pending["previous"] = previous
                pending["rotate"] = rotate
                server_proof = self.repair_proof(
                    previous, pairing_id, invitation, "desktop"
                )
            pickup = secrets.token_urlsafe(32)
            pending.update(
                status="approved" if pending.get("preauthorized") else "pending",
                display_name=display_name.strip(),
                platform=platform,
                pickup_hash=_digest(pickup),
            )
            del pending["invitation_hash"]
            return {
                "pickup_secret": pickup,
                "expires_at": pending["expires_at"],
                **({"server_proof": server_proof} if server_proof else {}),
            }

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
            previous = self._grants.get(pending.get("previous", ""))
            if pending.get("previous") and previous is None:
                raise PairingError("Previous authorization was revoked")
            if (
                previous
                and previous.permissions == pending["permissions"]
                and not pending.get("rotate")
            ):
                del self._pending[pairing_id]
                return {
                    "status": "approved",
                    "reused": True,
                    "device": previous.model_dump(),
                }
            token = secrets.token_urlsafe(32)
            grant = ClientGrant(
                device_id=previous.device_id if previous else secrets.token_hex(16),
                provisional_until=time.time() + self.TTL if previous else None,
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
            if (
                grant
                and grant.provisional_until is not None
                and grant.provisional_until <= time.time()
            ):
                return None
            return grant.model_copy(deep=True) if grant else None

    def confirm(self, token: str) -> bool:
        """Retire predecessors only after the phone has durably saved its token."""
        with self._lock:
            grant = self.verify(token)
            if grant is None:
                return False
            if grant.provisional_until is None:
                return True
            digest = _digest(token)
            grants = {
                key: value
                for key, value in self._grants.items()
                if value.device_id != grant.device_id or key == digest
            }
            grants[digest] = grant.model_copy(update={"provisional_until": None})
            self._save(grants)
            return True

    def devices(self) -> list[dict]:
        with self._lock:
            devices = {}
            for grant in self._grants.values():
                if grant.provisional_until is None:
                    devices[grant.device_id] = grant.model_dump()
            return list(devices.values())

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
