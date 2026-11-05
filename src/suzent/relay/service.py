"""The relay connection the user configured in Settings → Mobile → Relay."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from starlette.types import ASGIApp

from suzent.core.secrets import SecretManager, get_secret_manager
from suzent.logger import get_logger
from suzent.relay.agent import (
    PathGate,
    RelayAgent,
    RelayState,
    new_channel_token,
    normalize_relay_url,
)

from suzent.relay.e2e import E2EEndpoint, RelayIdentity, b64url

logger = get_logger(__name__)

KEY_SECRET = "SUZENT_RELAY::registration_key"
WEBHOOK_CHANNEL_SECRET = "SUZENT_RELAY::webhook_channel"
PHONE_CHANNEL_SECRET = "SUZENT_RELAY::phone_channel"
_SEVERITY = {
    RelayState.CONNECTED: 0,
    RelayState.STOPPED: 1,
    RelayState.CONNECTING: 2,
    RelayState.REPLACED: 3,
    RelayState.REJECTED: 4,
}


def _suzent_version() -> str:
    try:
        return version("suzent")
    except PackageNotFoundError:
        return ""


class RelayService:
    """Owns the relay settings and the agents that keep each channel open.

    The relay URL and on/off switch live in ``relay.json``; the registration
    key and channel tokens live in the secret store and are never returned to
    the UI except as URLs the user asked for.
    """

    def __init__(
        self,
        app: ASGIApp,
        config_path: Path,
        secrets: SecretManager | None = None,
    ) -> None:
        self.app = app
        self.config_path = config_path
        self.secrets = secrets or get_secret_manager()
        self.lock = asyncio.Lock()
        self.url: str | None = None
        self.enabled = False
        self.webhook_agent: RelayAgent | None = None
        self.phone_agent: RelayAgent | None = None
        self._identity: RelayIdentity | None = None
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            logger.warning("Ignoring unreadable relay settings")
            return
        url = data.get("url")
        self.url = url if isinstance(url, str) and url else None
        self.enabled = bool(data.get("enabled")) and self.url is not None

    def _save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"url": self.url, "enabled": self.enabled}), encoding="utf-8"
        )
        os.replace(tmp, self.config_path)

    def _channel_token(self, secret: str) -> str:
        token = self.secrets.get_backend_only(secret)
        if not token:
            token = new_channel_token()
            self.secrets.set_backend_only(secret, token)
        return token

    async def start(self) -> None:
        async with self.lock:
            await self._restart()

    async def stop(self) -> None:
        async with self.lock:
            await self._stop_agents()

    @property
    def identity(self) -> RelayIdentity:
        if self._identity is None:
            self._identity = RelayIdentity(
                self.config_path.parent / "relay_identity.pem"
            )
        return self._identity

    async def _stop_agents(self) -> None:
        agents = (self.webhook_agent, self.phone_agent)
        self.webhook_agent = self.phone_agent = None
        for agent in agents:
            if agent is not None:
                await agent.stop()

    def _agent(self, token: str, app: ASGIApp, label: str) -> RelayAgent:
        assert self.url is not None
        agent = RelayAgent(
            self.url,
            token,
            app,
            key=self.secrets.get_backend_only(KEY_SECRET),
            name=socket.gethostname()[:100],
            version=_suzent_version(),
            label=label,
        )
        agent.start()
        return agent

    async def _restart(self) -> None:
        # Imported here: the gateway module pulls in uvicorn and TLS helpers.
        from suzent.mobile.tls import MobileGateway

        await self._stop_agents()
        if not (self.enabled and self.url):
            return
        self.webhook_agent = self._agent(
            self._channel_token(WEBHOOK_CHANNEL_SECRET),
            PathGate(self.app, http_prefixes=("/hooks/",)),
            "webhooks",
        )
        # Phones get the same surface as the LAN mobile gateway, but only
        # inside the encrypted tunnel; the relay itself can reach nothing.
        phone_token = self._channel_token(PHONE_CHANNEL_SECRET)
        self.phone_agent = self._agent(
            phone_token,
            E2EEndpoint(MobileGateway(self.app), self.identity, phone_token),
            "phones",
        )

    async def configure(
        self, *, url: str | None, key: str | None, enabled: bool
    ) -> None:
        """Save new settings and reconnect.

        ``key`` of ``None`` keeps the stored registration key; an empty string
        removes it. Raises ``ValueError`` for a malformed URL.
        """
        normalized = normalize_relay_url(url) if url else None
        if enabled and normalized is None:
            raise ValueError("A relay URL is required")
        async with self.lock:
            self.url = normalized
            self.enabled = enabled
            if key is not None:
                if key:
                    self.secrets.set_backend_only(KEY_SECRET, key)
                else:
                    self.secrets.delete(KEY_SECRET)
            self._save()
            await self._restart()
        logger.info("Relay settings updated (enabled={})", enabled)

    async def reset_channels(self) -> None:
        """Issue new channel tokens, so every old relay URL stops working."""
        async with self.lock:
            self.secrets.delete(WEBHOOK_CHANNEL_SECRET)
            self.secrets.delete(PHONE_CHANNEL_SECRET)
            await self._restart()
        logger.info("Relay channels reset")

    def webhook_url(self, path: str) -> str | None:
        """The relay address for a webhook path, when the relay is set up."""
        if self.webhook_agent is None:
            return None
        return self.webhook_agent.public_url(path)

    def phone_descriptor(self) -> dict[str, Any] | None:
        """What a phone needs to reach this desktop through the relay.

        Goes into the pairing QR code and the paired session, never anywhere
        the relay can read it.
        """
        if self.phone_agent is None:
            return None
        return {
            "version": 1,
            "url": self.phone_agent.base_url,
            "channel": self.phone_agent.token,
            "key": b64url(self.identity.public),
        }

    def status(self) -> dict[str, Any]:
        # Both channels share the relay and the key, so show whichever is
        # doing worse.
        statuses = [a.status for a in (self.webhook_agent, self.phone_agent) if a]
        state = max(statuses, key=lambda s: _SEVERITY[s.state], default=None)
        return {
            "url": self.url,
            "enabled": self.enabled,
            "has_key": bool(self.secrets.get_backend_only(KEY_SECRET)),
            "state": state.state.value if state else RelayState.STOPPED.value,
            "detail": state.detail if state else None,
            "protocol": state.protocol if state else None,
        }
