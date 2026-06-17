"""
Manager for connected nodes.
Responsible for node registry, lookup, command dispatch, and — for approve-mode
auth — a registry of pending connections awaiting operator approval.
"""

import asyncio
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any

from suzent.logger import get_logger
from suzent.nodes.base import NodeBase
from suzent.nodes.device_store import DeviceTokenStore

logger = get_logger(__name__)

# Pairing codes are short, single-use, and short-lived (operator approval window).
_PAIRING_CODE_CHARS = string.ascii_uppercase + string.digits
_PAIRING_CODE_LEN = 6
PENDING_TTL_SECONDS = 600  # 10 minutes, matching the social pairing window


@dataclass
class PendingConnection:
    """A node connection parked in approve mode, awaiting operator action."""

    pairing_code: str
    display_name: str
    platform: str
    capabilities: list[Any]
    requested_at: float = field(default_factory=time.time)
    # Resolved True (approved) or False (denied) by the operator action; the
    # waiting WebSocket handler awaits this.
    future: asyncio.Future = field(default=None)  # type: ignore[assignment]


class NodeManager:
    """
    Central coordinator for all connected nodes.
    Mirrors ChannelManager pattern.
    """

    def __init__(self, device_store: DeviceTokenStore | None = None):
        self.nodes: dict[str, NodeBase] = {}
        # Approve-mode pairing state, keyed by single-use pairing code.
        self._pending: dict[str, PendingConnection] = {}
        self.device_store = device_store or DeviceTokenStore()

    def register_node(self, node: NodeBase) -> None:
        """
        Add a node to the registry.

        Args:
            node: The node instance to register.
        """
        logger.info(
            f"Registering node: {node.display_name} ({node.node_id}) "
            f"with {len(node.capabilities)} capabilities"
        )
        self.nodes[node.node_id] = node

    def unregister_node(self, node_id: str) -> bool:
        """
        Remove a node from the registry.

        Args:
            node_id: The unique ID of the node to remove.

        Returns:
            True if the node was found and removed, False otherwise.
        """
        node = self.nodes.pop(node_id, None)
        if node:
            node.status = "disconnected"
            logger.info(f"Unregistered node: {node.display_name} ({node_id})")
            return True
        logger.warning(f"Attempted to unregister unknown node: {node_id}")
        return False

    def get_node(self, node_id_or_name: str) -> NodeBase | None:
        """
        Lookup a node by ID or display name.

        Args:
            node_id_or_name: Node ID or display name.

        Returns:
            The matching node, or None.
        """
        # Try direct ID lookup first
        if node_id_or_name in self.nodes:
            return self.nodes[node_id_or_name]

        # Fallback: search by display_name (case-insensitive)
        lower = node_id_or_name.lower()
        if lower == "host":
            lower = "local pc"

        for node in self.nodes.values():
            if node.display_name.lower() == lower:
                return node

        return None

    def list_nodes(self) -> list[dict[str, Any]]:
        """
        List all registered nodes with their status and capabilities.

        Returns:
            List of node info dicts.
        """
        return [node.to_dict() for node in self.nodes.values()]

    async def invoke(
        self,
        node_id_or_name: str,
        command: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Dispatch a command to a specific node.

        Args:
            node_id_or_name: Node ID or display name.
            command: The command to invoke.
            params: Optional parameters for the command.
            timeout: Optional override for how long to wait on the response
                (seconds). Long-running commands like ``agent.run`` need this.

        Returns:
            The result dict from the node.

        Raises:
            ValueError: If the node is not found or doesn't have the capability.
        """
        node = self.get_node(node_id_or_name)
        if not node:
            raise ValueError(f"Node not found: {node_id_or_name}")

        if node.status != "connected":
            raise ValueError(
                f"Node '{node.display_name}' is {node.status}, cannot invoke"
            )

        if not node.has_capability(command):
            available = ", ".join(cap.name for cap in node.capabilities)
            raise ValueError(
                f"Node '{node.display_name}' does not support command '{command}'. "
                f"Available: {available}"
            )

        logger.info(
            f"Invoking '{command}' on node '{node.display_name}' ({node.node_id})"
        )
        return await node.invoke(command, params, timeout=timeout)

    def describe_node(self, node_id_or_name: str) -> dict[str, Any] | None:
        """
        Get detailed info about a node including capabilities.

        Args:
            node_id_or_name: Node ID or display name.

        Returns:
            Node info dict, or None if not found.
        """
        node = self.get_node(node_id_or_name)
        if node:
            return node.to_dict()
        return None

    @property
    def connected_count(self) -> int:
        """Number of currently connected nodes."""
        return sum(1 for n in self.nodes.values() if n.status == "connected")

    # ── Approve-mode pairing ─────────────────────────────────────────

    def _generate_pairing_code(self) -> str:
        while True:
            code = "".join(
                secrets.choice(_PAIRING_CODE_CHARS) for _ in range(_PAIRING_CODE_LEN)
            )
            if code not in self._pending:
                return code

    def _expire_pending(self) -> None:
        """Drop pending entries past their TTL (rejecting their waiters)."""
        now = time.time()
        for code in [
            c
            for c, p in self._pending.items()
            if now - p.requested_at > PENDING_TTL_SECONDS
        ]:
            entry = self._pending.pop(code, None)
            if entry and entry.future and not entry.future.done():
                entry.future.set_result(False)

    def add_pending(
        self,
        display_name: str,
        platform: str,
        capabilities: list[Any],
        future: asyncio.Future,
    ) -> str:
        """Register a connection awaiting approval. Returns its pairing code."""
        self._expire_pending()
        code = self._generate_pairing_code()
        self._pending[code] = PendingConnection(
            pairing_code=code,
            display_name=display_name,
            platform=platform,
            capabilities=capabilities,
            future=future,
        )
        logger.info(
            f"Node '{display_name}' pending approval (code={code}, platform={platform})"
        )
        return code

    def cancel_pending(self, pairing_code: str) -> None:
        """Remove a pending entry (e.g. node disconnected before approval)."""
        self._pending.pop(pairing_code, None)

    def list_pending(self) -> list[dict[str, Any]]:
        """List connections awaiting operator approval."""
        self._expire_pending()
        return [
            {
                "pairing_code": p.pairing_code,
                "display_name": p.display_name,
                "platform": p.platform,
                "capabilities": [
                    {
                        "name": c.name,
                        "description": c.description,
                        "params_schema": c.params_schema,
                    }
                    for c in p.capabilities
                ],
                "requested_at": _iso(p.requested_at),
            }
            for p in self._pending.values()
        ]

    def approve_pending(self, pairing_code: str) -> tuple[bool, str]:
        """Approve a pending connection and mint a durable device token.

        Returns (success, device_token). The waiting WebSocket handler resolves
        and completes registration; the token is handed to the node to persist.
        """
        self._expire_pending()
        entry = self._pending.pop(pairing_code, None)
        if not entry:
            return False, ""
        _device_id, token = self.device_store.mint(entry.display_name, entry.platform)
        if entry.future and not entry.future.done():
            entry.future.set_result(token)
        return True, token

    def deny_pending(self, pairing_code: str) -> bool:
        """Deny a pending connection (rejecting its waiter)."""
        entry = self._pending.pop(pairing_code, None)
        if not entry:
            return False
        if entry.future and not entry.future.done():
            entry.future.set_result(False)
        return True

    # ── Durable approved devices ─────────────────────────────────────

    def list_devices(self) -> list[dict[str, Any]]:
        """List durably-approved devices, flagging which are connected now."""
        connected_names = {
            n.display_name for n in self.nodes.values() if n.status == "connected"
        }
        out = []
        for dev in self.device_store.list_devices():
            out.append({**dev, "connected": dev["display_name"] in connected_names})
        return out

    def revoke_device(self, device_id: str) -> bool:
        """Revoke a durable device token by device_id."""
        return self.device_store.revoke(device_id)


def _iso(ts: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
