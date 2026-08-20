"""
Registry of external A2A agents this device may delegate to.

The mirror of ``PeerGrantStore``: that holds Suzent peers reached through the
pairing ritual, this holds agents reached by URL. An entry is created when the
operator adds an agent's address — we fetch its Agent Card, keep the parts we
need to call it, and remember any credential the operator supplied.

The card is cached because it is a public document that changes rarely, and a
delegating agent should not have to re-fetch it on every turn. ``refresh`` picks
up changes on demand.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from suzent.config import USER_CONFIG_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)

_STORE_PATH = USER_CONFIG_DIR / "a2a_agents.json"
_default_store: "A2AAgentStore | None" = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class A2AAgentStore:
    """Persists external A2A agents to ``a2a_agents.json``.

    File shape::

        {"agents": {"<agent_id>": {
            "name": "...", "base_url": "https://host",
            "rpc_url": "https://host/a2a/v1", "token": "...",
            "enabled": true, "card": {...}, "added_at": "<iso>"}}}
    """

    def __init__(self, path=_STORE_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._agents: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                with open(self._path, encoding="utf-8") as handle:
                    self._agents = (json.load(handle) or {}).get("agents", {}) or {}
        except Exception as exc:
            logger.warning("A2A store: could not load {}: {}", self._path, exc)
            self._agents = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as handle:
                json.dump({"agents": self._agents}, handle, indent=2)
        except Exception as exc:
            logger.warning("A2A store: could not persist {}: {}", self._path, exc)

    def add(
        self,
        *,
        base_url: str,
        rpc_url: str,
        name: str,
        card: dict[str, Any] | None = None,
        token: str = "",
    ) -> str:
        """Add or update an agent, keeping its id stable across re-adds."""
        with self._lock:
            normalized = base_url.rstrip("/")
            agent_id = next(
                (
                    aid
                    for aid, record in self._agents.items()
                    if record.get("base_url") == normalized
                ),
                uuid.uuid4().hex[:12],
            )
            previous = self._agents.get(agent_id, {})
            self._agents[agent_id] = {
                "name": name,
                "base_url": normalized,
                "rpc_url": rpc_url,
                # Re-adding without a token keeps the one already stored, so a
                # refresh never silently drops the operator's credential.
                "token": token or previous.get("token", ""),
                "enabled": previous.get("enabled", True),
                "card": card if card is not None else previous.get("card"),
                "added_at": previous.get("added_at") or _now_iso(),
            }
            self._save()
        return agent_id

    def get(self, agent_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._agents.get(agent_id)
            return dict(record) if record else None

    def set_enabled(self, agent_id: str, enabled: bool) -> bool:
        with self._lock:
            record = self._agents.get(agent_id)
            if not record:
                return False
            record["enabled"] = bool(enabled)
            self._save()
            return True

    def list_agents(self) -> list[dict[str, Any]]:
        """List agents without exposing stored tokens."""
        with self._lock:
            return [
                {
                    "agent_id": aid,
                    "name": record.get("name", ""),
                    "base_url": record.get("base_url", ""),
                    "rpc_url": record.get("rpc_url", ""),
                    "enabled": bool(record.get("enabled", True)),
                    "has_token": bool(record.get("token")),
                    "card": record.get("card"),
                    "added_at": record.get("added_at", ""),
                }
                for aid, record in self._agents.items()
            ]

    def remove(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id not in self._agents:
                return False
            del self._agents[agent_id]
            self._save()
            return True


def get_a2a_agent_store() -> A2AAgentStore:
    """Return the process-wide external-agent registry."""
    global _default_store
    if _default_store is None:
        _default_store = A2AAgentStore()
    return _default_store
