"""Local Agent Client Protocol (ACP) integration.

Both directions live here: :mod:`suzent.acp.client` drives external ACP agents
as subagents, and :mod:`suzent.acp.server` serves this Suzent *as* an ACP agent
to an external client.
"""

from .manager import ACPManager, get_acp_manager
from .registry import ACPAgent, ACPAgentRegistry
from .server import ACPAgentServer, SuzentBackend, serve_stdio

__all__ = [
    "ACPAgent",
    "ACPAgentRegistry",
    "ACPAgentServer",
    "ACPManager",
    "SuzentBackend",
    "get_acp_manager",
    "serve_stdio",
]
