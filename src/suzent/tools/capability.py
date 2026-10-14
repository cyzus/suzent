"""Pydantic AI capability for a selected group of registered tools."""

import traceback
from dataclasses import dataclass
from typing import Any, Sequence

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger
from suzent.permissions.audit import redact_secrets

logger = get_logger(__name__)

# Long enough for a traceback's last line, short enough not to flood context.
_TOOL_ERROR_MESSAGE_LIMIT = 2000


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


@dataclass
class ToolErrorCapability(AbstractCapability[AgentDeps]):
    """Report a tool that raised as a failed call instead of ending the turn.

    pydantic-ai re-raises a tool's exception by default, which aborts the whole
    run: the turn stops with an error and the call never gets a result. Any
    tool that does not catch its own failures -- a crawler or database error, a
    dropped MCP connection -- did that. Converting the exception to
    ``ToolFailed`` gives the model a failed result it can adapt to, and the
    call is shown as failed. Cancellation is a ``BaseException`` and is not
    caught here, so stopping a turn still stops it.
    """

    async def on_tool_execute_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        # The message goes to the model and into stored history, and exception
        # text from clients and MCP servers can carry credentials. Logging the
        # traceback as formatted text, not via loguru's exception hook, keeps
        # local variable values out of the log too.
        detail = redact_secrets(f"{type(error).__name__}: {error}")
        logger.warning(
            "Tool {} raised; reporting it as a failed call: {}",
            call.tool_name,
            detail[:_TOOL_ERROR_MESSAGE_LIMIT],
        )
        logger.debug(
            "Tool {} traceback:\n{}",
            call.tool_name,
            redact_secrets("".join(traceback.format_exception(error))),
        )
        raise ToolFailed(
            f"The tool failed with an error. {detail[:_TOOL_ERROR_MESSAGE_LIMIT]}"
        ) from error
