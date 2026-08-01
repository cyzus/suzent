"""Pydantic AI capability for a selected group of registered tools."""

from dataclasses import dataclass
from typing import Sequence

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from suzent.core.agent_deps import AgentDeps


@dataclass
class RegisteredToolCapability(AbstractCapability[AgentDeps]):
    """Bundle selected registry tools under one capability boundary."""

    capability_id: str
    tool_names: Sequence[str]

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        from suzent.tools.registry import get_tool_function

        tools = [
            tool
            for name in self.tool_names
            if (tool := get_tool_function(name)) is not None
        ]
        return FunctionToolset(tools, id=f"suzent-{self.capability_id}")
