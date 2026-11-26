"""Authenticated, local-only request transport to one paired browser profile."""

import asyncio
import hashlib
import json
import secrets
import time

from suzent.config.paths import USER_CONFIG_DIR
from suzent.tools.browser.bridge import (
    BridgeHello as ExtensionHello,
    BridgeMessage as ExtensionMessage,
    BrowserBridge,
)

__all__ = ["ExtensionBridge", "ExtensionHello", "ExtensionMessage", "bridge"]


class ExtensionBridge(BrowserBridge):
    not_connected = "Connect the Suzent browser extension in Settings → Browser first."
    disconnected_message = (
        "Browser extension disconnected. Reconnect it in Settings → Browser."
    )
    timeout_message = "Browser extension timed out. Reconnect and take a fresh snapshot before retrying."

    def __init__(self) -> None:
        super().__init__()
        self.pairing_lock = asyncio.Lock()
        self._pairing: tuple[str, float] | None = None

    def create_pairing(self) -> str:
        token = secrets.token_urlsafe(32)
        self._pairing = (self._digest(token), time.monotonic() + 300)
        return token

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def authenticate(self, token: str, origin: str) -> bool:
        digest = self._digest(token)
        path = USER_CONFIG_DIR / "browser-extension.json"
        if (
            self._pairing
            and time.monotonic() < self._pairing[1]
            and secrets.compare_digest(digest, self._pairing[0])
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"digest": digest, "origin": origin}), encoding="utf-8"
            )
            temporary.replace(path)
            self._pairing = None
            return True
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            return saved["origin"] == origin and secrets.compare_digest(
                saved["digest"], digest
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False

    async def revoke(self) -> None:
        self._pairing = None
        (USER_CONFIG_DIR / "browser-extension.json").unlink(missing_ok=True)
        socket = self.socket
        try:
            if socket:
                await socket.close(code=1008)
        finally:
            if self.socket is socket:
                await self.disconnected()


bridge = ExtensionBridge()
