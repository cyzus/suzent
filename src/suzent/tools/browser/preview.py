"""Bounded, best-effort delivery of browser preview frames."""

import asyncio
from typing import Any

from starlette.websockets import WebSocket


class PreviewFrames:
    def __init__(self, clients: list[WebSocket]) -> None:
        self.clients = clients
        self.pending: dict[str, Any] | None = None
        self.task: asyncio.Task[None] | None = None

    def offer(self, message: dict[str, Any]) -> None:
        if not self.clients:
            return
        # Only the newest frame matters when rendering falls behind.
        self.pending = message
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._send())

    async def _send(self) -> None:
        while self.pending is not None and self.clients:
            message, self.pending = self.pending, None
            for client in list(self.clients):
                try:
                    await asyncio.wait_for(client.send_json(message), timeout=1)
                except Exception:
                    if client in self.clients:
                        self.clients.remove(client)
                    try:
                        await asyncio.wait_for(client.close(code=1013), timeout=1)
                    except Exception:
                        pass
            await asyncio.sleep(0.1)

    async def clear(self) -> None:
        self.pending = None
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
