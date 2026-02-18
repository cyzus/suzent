"""
In-process local node — registers directly with the NodeManager,
dispatching to the same handlers as the standalone node host.

No WebSocket overhead — runs inside the server process.
"""

import sys
import uuid
from typing import Any

from suzent.logger import get_logger
from suzent.nodes.base import NodeBase, NodeCapability
from suzent.nodes.node_host import _HANDLERS

logger = get_logger(__name__)


class LocalNode(NodeBase):
    """A node running inside the server process itself.

    Exposes the local machine's hardware (speaker, camera, etc.)
    without requiring a separate process or WebSocket connection.
    """

    def __init__(
        self,
        display_name: str = "Local PC",
        platform: str = sys.platform,
        capabilities: list[str] | None = None,
    ):
        if capabilities:
            handlers = {k: v for k, v in _HANDLERS.items() if k in capabilities}
        else:
            handlers = dict(_HANDLERS)

        caps = [
            NodeCapability(
                name=meta["name"],
                description=meta["description"],
                params_schema=meta["params_schema"],
            )
            for fn in handlers.values()
            for meta in [fn._capability_meta]  # type: ignore[attr-defined]
        ]

        node_id = f"local-{uuid.uuid4().hex[:8]}"
        super().__init__(
            node_id=node_id,
            display_name=display_name,
            platform=platform,
            capabilities=caps,
        )
        self._handlers = handlers

    async def invoke(
        self, command: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Dispatch to local handler — same handlers as the standalone node host."""
        handler = self._handlers.get(command)
        if not handler:
            return {"success": False, "error": f"Unknown command: {command}"}

        try:
            result = await handler(params or {})
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Local node handler error for {command}: {e}")
            return {"success": False, "error": str(e)}

    async def heartbeat(self) -> bool:
        """Local node is always alive."""
        return True
