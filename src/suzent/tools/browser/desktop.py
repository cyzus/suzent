"""The desktop app's built-in browser, driven over a local token-checked bridge.

The Suzent desktop app hosts the agent's pages in its own window and relays
Chrome DevTools Protocol commands for them. It connects as a WebSocket
client and proves it runs as the same user by echoing a token that only this
backend writes, to a file only that user can read.
"""

import asyncio
import os
import secrets
from pathlib import Path

from pydantic import ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect

from suzent.auth_boundary import is_loopback
from suzent.config.paths import RUNTIME_DIR
from suzent.logger import get_logger
from suzent.tools.browser.bridge import BridgeHello, BrowserBridge
from suzent.tools.browser.extension.session import BridgeSession

logger = get_logger(__name__)


def token_path(port: int) -> Path:
    return RUNTIME_DIR / f"desktop-browser-{port}.token"


class DesktopBridge(BrowserBridge):
    not_connected = (
        "The Suzent app's built-in browser is not connected. Open the Suzent app."
    )
    disconnected_message = (
        "The Suzent app's built-in browser closed. Open the Suzent app and retry."
    )
    timeout_message = (
        "The Suzent app's browser timed out. Take a fresh snapshot before retrying."
    )

    def __init__(self) -> None:
        super().__init__()
        self.lock = asyncio.Lock()
        self._token = secrets.token_urlsafe(32)
        self._port: int | None = None

    def publish(self, port: int) -> None:
        """Write the token where the desktop app (same user) can read it."""
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        path = token_path(port)
        path.unlink(missing_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(self._token)
        self._port = port

    def unpublish(self) -> None:
        if self._port is not None:
            token_path(self._port).unlink(missing_ok=True)
            self._port = None

    def authenticate(self, token: str) -> bool:
        return secrets.compare_digest(token, self._token)


desktop_bridge = DesktopBridge()
desktop_session = BridgeSession(desktop_bridge)


def effective_mode(mode: str) -> str:
    """The mode actually in use: "desktop" without the app open means "managed"."""
    if mode == "desktop" and desktop_bridge.socket is None:
        return "managed"
    return mode


async def desktop_browser_websocket(websocket: WebSocket) -> None:
    # Web pages always send Origin; the app's main process sends none.
    if (
        not websocket.client
        or not is_loopback(websocket.client.host)
        or "origin" in websocket.headers
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        hello = BridgeHello.model_validate(
            await asyncio.wait_for(websocket.receive_json(), timeout=5)
        )
        async with desktop_bridge.lock:
            if not desktop_bridge.authenticate(hello.token):
                await websocket.close(code=1008)
                return
            await desktop_bridge.adopt(websocket)
            await websocket.send_json({"type": "ready"})
        logger.info("Desktop app browser connected")
        await desktop_bridge.serve(websocket)
    except (WebSocketDisconnect, TimeoutError, ValidationError, ValueError, OSError):
        try:
            await websocket.close(code=1008)
        except RuntimeError:
            pass
    finally:
        if desktop_bridge.socket is websocket:
            await desktop_bridge.disconnected()
            logger.info("Desktop app browser disconnected")
