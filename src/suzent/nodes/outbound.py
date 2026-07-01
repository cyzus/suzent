"""
Outbound node connections — the "join another Suzent" / click-to-pair side.

When this device wants to become a *node* of a remote server, it runs a
``NodeHost`` outbound to that server's gateway. This manager owns those
NodeHost instances (one per remote gateway) and their background tasks, and
surfaces their live state (connecting / pending / connected / error) so the UI
can show pairing codes and connection status.
"""

import asyncio
import socket

from suzent.logger import get_logger
from suzent.nodes.node_host import NodeHost

logger = get_logger(__name__)


class OutboundConnectionManager:
    """Tracks outbound NodeHost connections keyed by remote gateway URL."""

    def __init__(self):
        self._conns: dict[str, dict] = {}

    def start(self, gateway_url: str, display_name: str = "") -> NodeHost:
        """Start (or return the existing) outbound connection to a gateway."""
        existing = self._conns.get(gateway_url)
        if existing and not existing["task"].done():
            return existing["host"]

        host = NodeHost(
            gateway_url=gateway_url,
            display_name=display_name or socket.gethostname(),
        )
        task = asyncio.create_task(host.run())
        self._conns[gateway_url] = {"host": host, "task": task}
        logger.info(f"Outbound: connecting to {gateway_url} as '{host.display_name}'")
        return host

    def list(self) -> list[dict]:
        """Snapshot of all outbound connections and their live state."""
        out = []
        for gw, c in self._conns.items():
            host: NodeHost = c["host"]
            done = c["task"].done()
            out.append(
                {
                    "gateway_url": gw,
                    "display_name": host.display_name,
                    "status": "stopped"
                    if done and host.status != "error"
                    else host.status,
                    "pairing_code": host.pairing_code,
                    "node_id": host.node_id,
                    "error": host.last_error,
                }
            )
        return out

    async def stop(self, gateway_url: str) -> bool:
        """Stop and forget an outbound connection."""
        c = self._conns.pop(gateway_url, None)
        if not c:
            return False
        c["host"].stop()
        c["task"].cancel()
        try:
            await c["task"]
        except (asyncio.CancelledError, Exception):
            pass
        logger.info(f"Outbound: stopped connection to {gateway_url}")
        return True

    async def stop_all(self) -> None:
        for gw in list(self._conns):
            await self.stop(gw)
