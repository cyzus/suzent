"""
Base classes and data models for the node system.

A node is a companion device that connects to the suzent server and
advertises capabilities (commands) the agent can invoke remotely.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NodeCapability:
    """
    Describes a single command a node can handle.

    Example:
        NodeCapability(
            name="camera.snap",
            description="Take a photo with the device camera",
            params_schema={"format": "str", "quality": "float"}
        )
    """

    name: str
    description: str = ""
    params_schema: dict[str, str] = field(default_factory=dict)


class NodeBase(ABC):
    """
    Abstract base class for nodes.

    Mirrors the SocialChannel pattern — each node type implements this ABC
    and the NodeManager orchestrates them.
    """

    def __init__(
        self,
        node_id: str,
        display_name: str,
        platform: str,
        capabilities: list[NodeCapability] | None = None,
    ):
        self.node_id = node_id
        self.display_name = display_name
        self.platform = platform
        self.capabilities: list[NodeCapability] = capabilities or []
        self.status: str = "connected"
        self.connected_at: datetime = datetime.now()

    @abstractmethod
    async def invoke(
        self, command: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Invoke a command on this node.

        Args:
            command: The capability command name (e.g., "camera.snap").
            params: Optional parameters for the command.

        Returns:
            Dict with at least {"success": bool, "result": Any}.
        """
        pass

    @abstractmethod
    async def heartbeat(self) -> bool:
        """
        Check if this node is still alive.

        Returns:
            True if node responded, False otherwise.
        """
        pass

    def has_capability(self, command: str) -> bool:
        """Check if this node advertises a given command."""
        return any(cap.name == command for cap in self.capabilities)

    def get_capability(self, command: str) -> NodeCapability | None:
        """Get capability descriptor by command name."""
        return next((cap for cap in self.capabilities if cap.name == command), None)

    def to_dict(self) -> dict[str, Any]:
        """Serialize node info for API responses."""
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "platform": self.platform,
            "status": self.status,
            "connected_at": self.connected_at.isoformat(),
            "capabilities": [
                {
                    "name": cap.name,
                    "description": cap.description,
                    "params_schema": cap.params_schema,
                }
                for cap in self.capabilities
            ],
        }
