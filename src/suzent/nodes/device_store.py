"""
Durable per-device token store for approve-mode node pairing.

When an operator approves a pending node, the server mints a long-lived
per-device token and persists it here. The node saves the token and presents
it on reconnect, skipping re-approval. Tokens are individually revocable.

Persistence mirrors the social allowlist convention (a JSON file in the user
config dir) so approvals survive restarts.
"""

import json
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from suzent.config import USER_CONFIG_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)

_STORE_PATH = USER_CONFIG_DIR / "node_devices.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeviceTokenStore:
    """Reads/writes durable per-device tokens to ``node_devices.json``.

    File shape::

        {"devices": {"<device_token>": {
            "device_id": "...", "display_name": "...",
            "platform": "...", "approved_at": "<iso>"}}}

    Tokens are the lookup key (O(1) auth check); ``device_id`` is the stable
    handle used for display and revocation.
    """

    def __init__(self, path=_STORE_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._devices: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                with open(self._path) as f:
                    data = json.load(f)
                self._devices = data.get("devices", {}) or {}
        except Exception as e:
            logger.warning(f"Device store: could not load {self._path}: {e}")
            self._devices = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w") as f:
                json.dump({"devices": self._devices}, f, indent=2)
        except Exception as e:
            logger.warning(f"Device store: could not persist {self._path}: {e}")

    def mint(
        self, display_name: str, platform: str, scope: str = "node"
    ) -> tuple[str, str]:
        """Create and persist a new device token. Returns (device_id, token).

        ``scope`` controls what a remote bearer of this token may reach:
        ``node`` (WS companion, no HTTP), ``agent`` (trigger the agent only), or
        ``full`` (host access — everything). Enforced in the auth boundary.
        """
        device_id = uuid.uuid4().hex[:12]
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._devices[token] = {
                "device_id": device_id,
                "display_name": display_name,
                "platform": platform,
                "scope": scope,
                "approved_at": _now_iso(),
            }
            self._save()
        logger.info(
            f"Device store: minted {scope} token for '{display_name}' ({device_id})"
        )
        return device_id, token

    def verify(self, token: str) -> dict[str, Any] | None:
        """Return the device record for a valid token, else None."""
        if not token:
            return None
        with self._lock:
            return self._devices.get(token)

    def list_devices(self) -> list[dict[str, Any]]:
        """List approved devices (without exposing the raw tokens)."""
        with self._lock:
            return [
                {
                    "device_id": rec["device_id"],
                    "display_name": rec.get("display_name", ""),
                    "platform": rec.get("platform", "unknown"),
                    "scope": rec.get("scope", "node"),
                    "approved_at": rec.get("approved_at", ""),
                }
                for rec in self._devices.values()
            ]

    def revoke(self, device_id: str) -> bool:
        """Remove a device by its device_id. Returns True if one was removed."""
        with self._lock:
            token = next(
                (
                    t
                    for t, r in self._devices.items()
                    if r.get("device_id") == device_id
                ),
                None,
            )
            if token is None:
                return False
            del self._devices[token]
            self._save()
        logger.info(f"Device store: revoked device {device_id}")
        return True
