"""Authenticated, local-only request transport to one paired browser profile."""

import asyncio
import hashlib
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from starlette.websockets import WebSocket

from suzent.config.paths import USER_CONFIG_DIR


REQUEST_TIMEOUT = 20.0


class ExtensionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["result", "event", "ping"]
    id: int | None = None
    result: Any = None
    error: str | None = Field(default=None, max_length=1000)
    method: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ExtensionHello(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class ExtensionBridge:
    def __init__(self) -> None:
        self.pairing_lock = asyncio.Lock()
        self.socket: WebSocket | None = None
        self.generation = 0
        self._counter = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._pairing: tuple[str, float] | None = None
        self.on_disconnect: Callable[[], Awaitable[None]] | None = None
        self.on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None

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

    async def disconnected(self) -> None:
        self.socket = None
        self.generation += 1
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    ValueError(
                        "Browser extension disconnected. Reconnect it in Settings → Browser."
                    )
                )
        self._pending.clear()
        if self.on_disconnect:
            await self.on_disconnect()

    async def request(self, action: str, **params: Any) -> Any:
        socket = self.socket
        if socket is None:
            raise ValueError(
                "Connect the Suzent browser extension in Settings → Browser first."
            )
        self._counter += 1
        request_id = self._counter
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await socket.send_json(
                {"id": request_id, "action": action, "params": params}
            )
            return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
        except TimeoutError:
            # Never replay a command whose outcome is unknown.
            try:
                if self.socket is socket:
                    await socket.close(code=1011)
            except (RuntimeError, OSError):
                pass
            finally:
                if self.socket is socket:
                    await self.disconnected()
            raise ValueError(
                "Browser extension timed out. Reconnect and take a fresh snapshot before retrying."
            ) from None
        finally:
            self._pending.pop(request_id, None)

    async def receive(self, message: ExtensionMessage) -> None:
        if message.type == "result":
            future = self._pending.get(message.id)
            if future and not future.done():
                if message.error:
                    future.set_exception(ValueError(message.error))
                else:
                    future.set_result(message.result)
        elif message.type == "event" and self.on_event:
            await self.on_event(message.method or "", message.params)


bridge = ExtensionBridge()
