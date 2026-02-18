"""
Node system for suzent.

Nodes are companion devices (desktop apps, mobile phones, headless servers)
that connect to the suzent server via WebSocket and expose capabilities
the agent can invoke through the CLI.
"""

from suzent.nodes.base import NodeBase, NodeCapability
from suzent.nodes.manager import NodeManager
from suzent.nodes.models import (
    ConnectMessage,
    ConnectedResponse,
    InvokeMessage,
    InvokeRequest,
    InvokeResponse,
    NodeInfo,
    NodeListResponse,
    ResultMessage,
)

__all__ = [
    "NodeBase",
    "NodeCapability",
    "NodeManager",
    "ConnectMessage",
    "ConnectedResponse",
    "InvokeMessage",
    "InvokeRequest",
    "InvokeResponse",
    "NodeInfo",
    "NodeListResponse",
    "ResultMessage",
]
