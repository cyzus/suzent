"""
Manager for connected nodes.
Responsible for node registry, lookup, and command dispatch.
"""

from typing import Any

from suzent.logger import get_logger
from suzent.nodes.base import NodeBase

logger = get_logger(__name__)


class NodeManager:
    """
    Central coordinator for all connected nodes.
    Mirrors ChannelManager pattern.
    """

    def __init__(self):
        self.nodes: dict[str, NodeBase] = {}

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
    ) -> dict[str, Any]:
        """
        Dispatch a command to a specific node.

        Args:
            node_id_or_name: Node ID or display name.
            command: The command to invoke.
            params: Optional parameters for the command.

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
        return await node.invoke(command, params)

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
