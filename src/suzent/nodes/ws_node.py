"""
WebSocket-based node implementation.

A WebSocketNode wraps a Starlette WebSocket connection from a companion device.
Commands are dispatched as JSON-RPC-style messages and responses are awaited.
"""

import asyncio
import uuid
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from suzent.logger import get_logger
from suzent.nodes.base import NodeBase, NodeCapability
from suzent.nodes.models import InvokeMessage, PingMessage, ResultMessage

logger = get_logger(__name__)

# Default timeout for waiting on node responses (seconds)
DEFAULT_INVOKE_TIMEOUT = 30.0


class WebSocketNode(NodeBase):
    """
    A node connected via WebSocket.

    Protocol:
        Client -> Server (on connect):
            {"type": "connect", "display_name": "iPhone", "platform": "ios",
             "capabilities": [{"name": "camera.snap", "description": "...", "params_schema": {...}}]}

        Server -> Client (invoke):
            {"type": "invoke", "request_id": "uuid", "command": "camera.snap", "params": {...}}

        Client -> Server (result):
            {"type": "result", "request_id": "uuid", "success": true, "result": {...}}
    """

    def __init__(
        self,
        websocket: WebSocket,
        node_id: str,
        display_name: str,
        platform: str,
        capabilities: list[NodeCapability] | None = None,
    ):
        super().__init__(node_id, display_name, platform, capabilities)
        self._ws = websocket
        self._pending: dict[str, asyncio.Future] = {}

    async def invoke(
        self, command: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Send a command to the node and wait for the response.

        Args:
            command: The command name to invoke.
            params: Optional parameters.

        Returns:
            Dict with {"success": bool, "result": Any}.

        Raises:
            TimeoutError: If the node doesn't respond within the timeout.
            ConnectionError: If the WebSocket is disconnected.
        """
        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            msg = InvokeMessage(
                request_id=request_id,
                command=command,
                params=params or {},
            )
            await self._ws.send_json(msg.model_dump())

            result = await asyncio.wait_for(future, timeout=DEFAULT_INVOKE_TIMEOUT)
            return result

        except asyncio.TimeoutError:
            logger.error(f"Timeout invoking '{command}' on node '{self.display_name}'")
            raise TimeoutError(
                f"Node '{self.display_name}' did not respond to '{command}' "
                f"within {DEFAULT_INVOKE_TIMEOUT}s"
            ) from None
        except WebSocketDisconnect:
            self.status = "disconnected"
            raise ConnectionError(
                f"Node '{self.display_name}' disconnected during invoke"
            )
        finally:
            self._pending.pop(request_id, None)

    async def heartbeat(self) -> bool:
        """Send a ping and check if the node responds."""
        try:
            await self._ws.send_json(PingMessage().model_dump())
            return True
        except Exception:
            self.status = "disconnected"
            return False

    def handle_message(self, data: dict[str, Any]) -> None:
        """Process an incoming message from the node WebSocket."""
        msg_type = data.get("type")

        if msg_type == "result":
            try:
                result = ResultMessage(**data)
            except Exception:
                logger.warning(f"Malformed result message from '{self.display_name}'")
                return

            if result.request_id in self._pending:
                future = self._pending[result.request_id]
                if not future.done():
                    future.set_result(
                        {
                            "success": result.success,
                            "result": result.result,
                            "error": result.error,
                        }
                    )
            else:
                logger.warning(
                    f"Received result for unknown request_id: {result.request_id}"
                )

        elif msg_type == "pong":
            logger.debug(f"Heartbeat pong from node '{self.display_name}'")

        elif msg_type == "event":
            # Future: handle node-initiated events (notifications, status changes)
            logger.info(f"Event from node '{self.display_name}': {data.get('event')}")

        else:
            logger.warning(
                f"Unknown message type '{msg_type}' from node '{self.display_name}'"
            )

    async def close(self) -> None:
        """Close the WebSocket connection to this node."""
        self.status = "disconnected"
        for request_id, future in self._pending.items():
            if not future.done():
                future.set_exception(ConnectionError("Node connection closing"))
        self._pending.clear()

        try:
            await self._ws.close()
        except Exception:
            pass
