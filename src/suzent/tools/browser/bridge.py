"""Request transport to one browser host that speaks the bridge protocol.

The browser extension and the desktop app's built-in browser both connect to
the backend over a local WebSocket and answer the same small set of actions
(``tabs``, ``select``, ``open``, ``cdp``, ``status``, ``focus``, ``detach``).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from starlette.websockets import WebSocket

REQUEST_TIMEOUT = 20.0


class BridgeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["result", "event", "ping"]
    id: int | None = None
    result: Any = None
    error: str | None = Field(default=None, max_length=1000)
    method: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class BridgeHello(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class BrowserBridge:
    not_connected = "Connect the browser first."
    disconnected_message = "Browser disconnected."
    timeout_message = "Browser timed out. Take a fresh snapshot before retrying."
    # Whether the host can open and close tabs for the agent.
    manages_tabs = False

    def __init__(self) -> None:
        self.socket: WebSocket | None = None
        self.generation = 0
        self._counter = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self.on_disconnect: Callable[[], Awaitable[None]] | None = None
        self.on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None

    async def disconnected(self) -> None:
        self.socket = None
        self.generation += 1
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ValueError(self.disconnected_message))
        self._pending.clear()
        if self.on_disconnect:
            await self.on_disconnect()

    async def adopt(self, websocket: WebSocket) -> None:
        """Make *websocket* the connection, closing any previous one."""
        previous = self.socket
        try:
            if previous:
                await previous.close(code=1000)
        except (RuntimeError, OSError):
            pass
        finally:
            if self.socket is previous:
                await self.disconnected()
        self.socket = websocket

    async def request(self, action: str, **params: Any) -> Any:
        socket = self.socket
        if socket is None:
            raise ValueError(self.not_connected)
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
            raise ValueError(self.timeout_message) from None
        finally:
            self._pending.pop(request_id, None)

    async def receive(self, message: BridgeMessage) -> None:
        if message.type == "result":
            future = self._pending.get(message.id)
            if future and not future.done():
                if message.error:
                    future.set_exception(ValueError(message.error))
                else:
                    future.set_result(message.result)
        elif message.type == "event" and self.on_event:
            await self.on_event(message.method or "", message.params)

    async def serve(self, websocket: WebSocket) -> None:
        """Read messages from an adopted *websocket* until it closes."""
        while True:
            raw = await websocket.receive_text()
            if self.socket is not websocket:
                return
            if len(raw) > 8_000_000:
                await websocket.close(code=1009)
                return
            message = BridgeMessage.model_validate_json(raw)
            if message.type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await self.receive(message)
