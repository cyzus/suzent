"""Pydantic AI capability that bundles Suzent shell operations."""

from dataclasses import dataclass
from typing import Sequence

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from suzent.core.agent_deps import AgentDeps


@dataclass
class ShellCapability(AbstractCapability[AgentDeps]):
    """Expose command execution and process management as one capability."""

    tool_names: Sequence[str] = (
        "RunCommandTool",
        "StartCommandTool",
        "CheckCommandTool",
        "StopCommandTool",
    )

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        # Import lazily to avoid a registry -> capability -> registry cycle.
        from suzent.tools.registry import get_tool_function

        tools = [
            tool
            for name in self.tool_names
            if (tool := get_tool_function(name)) is not None
        ]
        return FunctionToolset(tools, id="suzent-shell")
