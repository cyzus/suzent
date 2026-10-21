"""Operator-approved ACP grants, separate from mobile and mesh credentials."""

import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def private_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ACPGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    grant_id: str
    client_name: str
    approved_at: float
    expires_at: float | None = None


class ACPPairingStore:
    TTL = 300
    MAX_PENDING = 32

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._pending: dict[str, dict[str, Any]] = {}
        self._grants = {
            digest: ACPGrant.model_validate(value)
            for digest, value in (
                json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            ).items()
        }

    def _save(self, grants: dict[str, ACPGrant]) -> None:
        private_write(
            self.path, {key: grant.model_dump() for key, grant in grants.items()}
        )
        self._grants = grants

    def _prune(self) -> None:
        self._pending = {
            key: value
            for key, value in self._pending.items()
            if value["expires_at"] > time.time()
        }

    def begin(self, client_name: str, token: str) -> dict[str, Any]:
        with self._lock:
            self._prune()
            digest = token_digest(token)
            if digest in self._grants or any(
                item["digest"] == digest for item in self._pending.values()
            ):
                raise ValueError("ACP credential already registered")
            if len(self._pending) >= self.MAX_PENDING:
                raise ValueError("Too many pending ACP requests")
            request_id = secrets.token_hex(16)
            entry = {
                "request_id": request_id,
                "client_name": client_name,
                "code": secrets.token_hex(3).upper(),
                "expires_at": time.time() + self.TTL,
                "status": "pending",
                "digest": token_digest(token),
            }
            self._pending[request_id] = entry
            return {key: value for key, value in entry.items() if key != "digest"}

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune()
            return [
                {key: value for key, value in item.items() if key != "digest"}
                for item in self._pending.values()
                if item["status"] == "pending"
            ]

    def decide(self, request_id: str, approved: bool) -> None:
        with self._lock:
            self._prune()
            entry = self._pending.get(request_id)
            if entry is None or entry["status"] != "pending":
                raise ValueError("ACP request unavailable")
            if approved:
                grant = ACPGrant(
                    grant_id=secrets.token_hex(16),
                    client_name=entry["client_name"],
                    approved_at=time.time(),
                    expires_at=entry["expires_at"],
                )
                self._save({**self._grants, entry["digest"]: grant})
            entry["status"] = "approved" if approved else "denied"

    def collect(self, request_id: str, token: str) -> dict[str, str]:
        with self._lock:
            self._prune()
            entry = self._pending.get(request_id)
            if entry is None or not secrets.compare_digest(
                entry["digest"], token_digest(token)
            ):
                raise ValueError("ACP request unavailable or expired")
            if entry["status"] == "approved":
                grant = self._grants.get(entry["digest"])
                if grant is None:
                    raise ValueError("ACP authorization was revoked")
                if grant.expires_at is not None:
                    self._save(
                        {
                            **self._grants,
                            entry["digest"]: grant.model_copy(
                                update={"expires_at": None}
                            ),
                        }
                    )
            return {"status": entry["status"]}

    def cancel(self, request_id: str, token: str) -> None:
        with self._lock:
            entry = self._pending.get(request_id)
            if entry is None or not secrets.compare_digest(
                entry["digest"], token_digest(token)
            ):
                raise ValueError("ACP request unavailable")
            if entry["status"] == "approved":
                self._save(
                    {
                        key: value
                        for key, value in self._grants.items()
                        if key != entry["digest"]
                    }
                )
            del self._pending[request_id]

    def verify(self, token: str) -> ACPGrant | None:
        with self._lock:
            grant = self._grants.get(token_digest(token))
            if grant and (grant.expires_at is None or grant.expires_at > time.time()):
                return grant
            return None

    def grants(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                grant.model_dump()
                for grant in self._grants.values()
                if grant.expires_at is None or grant.expires_at > time.time()
            ]

    def revoke(self, grant_id: str) -> None:
        with self._lock:
            self._save(
                {
                    key: grant
                    for key, grant in self._grants.items()
                    if grant.grant_id != grant_id
                }
            )
