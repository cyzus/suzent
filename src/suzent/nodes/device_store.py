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
import time
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

    # Min seconds between disk persists of trigger stats — keeps a chatty peer
    # from rewriting the whole store on every turn (stats are low-value telemetry).
    _TRIGGER_SAVE_INTERVAL = 30.0

    def __init__(self, path=_STORE_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._devices: dict[str, dict[str, Any]] = {}
        self._last_trigger_save: float = 0.0
        self._load()

    def _find_locked(self, device_id: str) -> tuple[str, dict[str, Any]] | None:
        """Return (token, record) for a device_id, or None. Caller holds the lock."""
        for token, rec in self._devices.items():
            if rec.get("device_id") == device_id:
                return token, rec
        return None

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
        self,
        display_name: str,
        platform: str,
        scope: str = "node",
        callback_url: str = "",
        node_identity: str = "",
    ) -> tuple[str, str]:
        """Create and persist a new device token. Returns (device_id, token).

        ``scope`` controls what a remote bearer of this token may reach:
        ``node`` (WS companion, no HTTP), ``agent`` (trigger the agent only), or
        ``full`` (host access — everything). Enforced in the auth boundary.
        ``callback_url`` is the holder's address, used to notify it if we later
        revoke this token (revocation propagation). ``node_identity`` is the
        holder's stable self-id (a label, for matching across networks).
        """
        device_id = uuid.uuid4().hex[:12]
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._devices[token] = {
                "device_id": device_id,
                "display_name": display_name,
                "platform": platform,
                "scope": scope,
                "status": "active",
                # A non-secret fingerprint (head…tail) so the UI can identify a
                # token after creation — the raw token is shown only once.
                "token_hint": f"{token[:6]}…{token[-4:]}",
                "callback_url": callback_url,
                "node_identity": node_identity,
                "approved_at": _now_iso(),
            }
            self._save()
        logger.info(
            f"Device store: minted {scope} token for '{display_name}' ({device_id})"
        )
        return device_id, token

    def get_by_device_id(self, device_id: str) -> dict[str, Any] | None:
        """Return a device record by its device_id (no token), else None."""
        with self._lock:
            for rec in self._devices.values():
                if rec.get("device_id") == device_id:
                    return dict(rec)
        return None

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
                    "status": rec.get("status", "active"),
                    "token_hint": rec.get("token_hint", ""),
                    # The holder's address — a stable join key so the UI can merge
                    # a grant with the peer record for the same machine (names
                    # differ: peer uses a display name, the grant the hostname).
                    "callback_url": rec.get("callback_url", ""),
                    "node_identity": rec.get("node_identity", ""),
                    "approved_at": rec.get("approved_at", ""),
                    "trigger_count": int(rec.get("trigger_count", 0)),
                    "last_triggered_at": rec.get("last_triggered_at", ""),
                }
                for rec in self._devices.values()
            ]

    def set_status(self, device_id: str, status: str) -> bool:
        """Set a device's grant status (``active`` | ``paused``).

        A ``paused`` grant keeps the durable token but is denied at the auth
        boundary, so the holder can be suspended without forcing a re-pair.
        Returns True if a device was updated.
        """
        if status not in ("active", "paused"):
            return False
        with self._lock:
            found = self._find_locked(device_id)
            if not found:
                return False
            found[1]["status"] = status
            self._save()
        logger.info(f"Device store: device {device_id} → {status}")
        return True

    def record_trigger(self, device_id: str) -> bool:
        """Record an inbound trigger from this device: bump count + last-used.

        Lets the Devices tab show usage stats ("last active", how many times a
        grant has driven us) so stale/over-active grants are easy to spot. The
        in-memory counters update every call, but the disk write is throttled
        (``_TRIGGER_SAVE_INTERVAL``) so a chatty peer doesn't rewrite the whole
        store on the inbound hot path. Returns True if a device was updated.
        """
        with self._lock:
            found = self._find_locked(device_id)
            if not found:
                return False
            rec = found[1]
            rec["trigger_count"] = int(rec.get("trigger_count", 0)) + 1
            rec["last_triggered_at"] = _now_iso()
            now = time.monotonic()
            if now - self._last_trigger_save >= self._TRIGGER_SAVE_INTERVAL:
                self._last_trigger_save = now
                self._save()
            return True

    def revoke(self, device_id: str) -> bool:
        """Remove a device by its device_id. Returns True if one was removed."""
        with self._lock:
            found = self._find_locked(device_id)
            if not found:
                return False
            del self._devices[found[0]]
            self._save()
        logger.info(f"Device store: revoked device {device_id}")
        return True

    def revoke_matching(self, node_identity: str = "", callback_url: str = "") -> int:
        """Revoke prior grants for the same machine. Returns count.

        Matches by ``node_identity`` when present (stable across networks), else
        falls back to ``callback_url`` (address). A machine that re-requests
        control would otherwise accumulate a new token per approval; superseding
        keeps one live grant per peer.
        """
        if not node_identity and not callback_url:
            return 0
        with self._lock:
            stale = [
                t
                for t, r in self._devices.items()
                if (node_identity and r.get("node_identity") == node_identity)
                or (
                    not node_identity
                    and callback_url
                    and r.get("callback_url") == callback_url
                )
            ]
            for t in stale:
                del self._devices[t]
            if stale:
                self._save()
        if stale:
            logger.info(
                f"Device store: superseded {len(stale)} prior grant(s) for "
                f"{node_identity or callback_url}"
            )
        return len(stale)
