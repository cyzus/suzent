"""
Controller-side store of peers this device may drive.

When a remote Suzent grants this device control, we persist the peer's address
and the grant token here so we can trigger its agent later (HTTP + token). This
is the mirror of DeviceTokenStore: that holds tokens we *issued* to others; this
holds tokens others *issued to us*.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from suzent.config import USER_CONFIG_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)

_STORE_PATH = USER_CONFIG_DIR / "node_peers.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PeerGrantStore:
    """Persists peers we can control to ``node_peers.json``.

    File shape::

        {"peers": {"<peer_id>": {
            "name": "...", "base_url": "http://host:port",
            "token": "...", "mode": "one_way|mutual|paused",
            "added_at": "<iso>"}}}
    """

    def __init__(self, path=_STORE_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._peers: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                with open(self._path) as f:
                    self._peers = (json.load(f) or {}).get("peers", {}) or {}
        except Exception as e:
            logger.warning(f"Peer store: could not load {self._path}: {e}")
            self._peers = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w") as f:
                json.dump({"peers": self._peers}, f, indent=2)
        except Exception as e:
            logger.warning(f"Peer store: could not persist {self._path}: {e}")

    def add(self, name: str, base_url: str, token: str, mode: str = "one_way") -> str:
        """Add (or update by base_url) a controllable peer. Returns peer_id."""
        with self._lock:
            peer_id = next(
                (p for p, r in self._peers.items() if r.get("base_url") == base_url),
                uuid.uuid4().hex[:12],
            )
            self._peers[peer_id] = {
                "name": name,
                "base_url": base_url.rstrip("/"),
                "token": token,
                "mode": mode,
                "added_at": _now_iso(),
            }
            self._save()
        return peer_id

    def get(self, peer_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._peers.get(peer_id)
            return dict(rec) if rec else None

    def set_mode(self, peer_id: str, mode: str) -> bool:
        with self._lock:
            rec = self._peers.get(peer_id)
            if not rec:
                return False
            rec["mode"] = mode
            self._save()
            return True

    def set_reverse_device_id(self, peer_id: str, device_id: str | None) -> bool:
        """Record (or clear) the device token WE minted so this peer can drive US."""
        with self._lock:
            rec = self._peers.get(peer_id)
            if not rec:
                return False
            if device_id:
                rec["reverse_device_id"] = device_id
            else:
                rec.pop("reverse_device_id", None)
            self._save()
            return True

    def list_peers(self) -> list[dict[str, Any]]:
        """List peers without exposing raw tokens."""
        with self._lock:
            return [
                {
                    "peer_id": pid,
                    "name": r.get("name", ""),
                    "base_url": r.get("base_url", ""),
                    "mode": r.get("mode", "one_way"),
                    "added_at": r.get("added_at", ""),
                }
                for pid, r in self._peers.items()
            ]

    def remove(self, peer_id: str) -> bool:
        with self._lock:
            if peer_id not in self._peers:
                return False
            del self._peers[peer_id]
            self._save()
            return True
