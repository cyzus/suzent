"""Sub-agent delegation and lifecycle tool exports.

Re-exports resolve on first attribute access, matching
:mod:`suzent.tools.filesystem` -- these modules pull in the agent runtime, so
eager re-exports would charge that cost to anything importing a single leaf.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from suzent.tools.agents.agent_lifecycle_tools import AgentListTool as AgentListTool
    from suzent.tools.agents.agent_lifecycle_tools import AgentReadTool as AgentReadTool
    from suzent.tools.agents.agent_lifecycle_tools import AgentSendTool as AgentSendTool
    from suzent.tools.agents.agent_lifecycle_tools import AgentStopTool as AgentStopTool
    from suzent.tools.agents.agent_tool import AgentTool as AgentTool

_EXPORTS = {
    "AgentTool": "suzent.tools.agents.agent_tool",
    "AgentListTool": "suzent.tools.agents.agent_lifecycle_tools",
    "AgentReadTool": "suzent.tools.agents.agent_lifecycle_tools",
    "AgentSendTool": "suzent.tools.agents.agent_lifecycle_tools",
    "AgentStopTool": "suzent.tools.agents.agent_lifecycle_tools",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
