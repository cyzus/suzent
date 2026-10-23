"""Pydantic AI capability for a selected group of registered tools."""

import traceback
from dataclasses import dataclass, replace
from typing import Any, Sequence

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import WrapModelRequestHandler
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger
from suzent.permissions.audit import redact_secrets

logger = get_logger(__name__)

# Long enough for a traceback's last line, short enough not to flood context.
_TOOL_ERROR_MESSAGE_LIMIT = 2000


@dataclass
class ToolResultContextCapability(AbstractCapability[AgentDeps]):
    """Keep display-only tool metadata out of requests, preserving stored history."""

    async def wrap_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        from suzent.tools.registry import get_model_excluded_metadata
        from suzent.tools.base import ToolResult

        excluded_by_tool = get_model_excluded_metadata()
        messages = []
        for message in request_context.messages:
            if not isinstance(message, ModelRequest):
                messages.append(message)
                continue
            parts = []
            for part in message.parts:
                excluded = excluded_by_tool.get(getattr(part, "tool_name", ""))
                content = getattr(part, "content", None)
                if excluded and isinstance(content, ToolResult):
                    content = content.model_dump(mode="json")
                if (
                    excluded
                    and isinstance(part, ToolReturnPart)
                    and isinstance(content, dict)
                    and isinstance(content.get("metadata"), dict)
                ):
                    content = {
                        **content,
                        "metadata": {
                            key: value
                            for key, value in content["metadata"].items()
                            if key not in excluded
                        },
                    }
                    part = replace(part, content=content)
                parts.append(part)
            messages.append(replace(message, parts=parts))
        return await handler(replace(request_context, messages=messages))


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
class ToolDenyCapability(AbstractCapability[AgentDeps]):
    """Withhold denied tools from the model, from execution and from ToolSearch.

    Unchecking a tool only demotes it to the ToolSearch pool, so "denied" needs
    its own layer. ``prepare_tools`` sees the assembled toolset -- our own
    tools, deferred ones and MCP tools alike -- and pydantic-ai wraps
    ``ToolSearch`` outside it, so a definition dropped here is neither offered,
    callable nor searchable. It runs every step, which is what lets an
    ``always_deny`` recorded mid-run take effect on the next request.
    """

    denied_names: frozenset[str] = frozenset()

    async def prepare_tools(
        self, ctx: RunContext[AgentDeps], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        policy = getattr(ctx.deps, "tool_approval_policy", {}) or {}
        if not self.denied_names and not policy:
            return tool_defs
        return [
            tool_def
            for tool_def in tool_defs
            if not is_denied(tool_def.name, self.denied_names, policy)
        ]

    async def before_tool_validate(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
    ) -> str | dict[str, Any]:
        allowed = getattr(ctx.deps, "call_allowed_tools", None)
        if allowed is not None and not is_call_allowed(call.tool_name, allowed):
            raise ToolFailed(
                f"{call.tool_name} is not available to this sub-agent. "
                "Use one of the tools it was given."
            )
        return args


def is_call_allowed(runtime_name: str, allowed: frozenset[str]) -> bool:
    """Whether a forked sub-agent may call a tool its parent's tool list offers.

    Mirrors what a non-forked sub-agent is given: its named tools, the builtins,
    and MCP tools, which ``tools_allowed`` never restricted.
    """
    from suzent.tools.names import BUILTIN_TOOL_NAMES
    from suzent.tools.registry import get_tool_class_name

    class_name = get_tool_class_name(runtime_name)
    if class_name is None or class_name in BUILTIN_TOOL_NAMES:
        return True
    return class_name in allowed or runtime_name in allowed


def is_denied(runtime_name: str, denied_names: frozenset[str], policy: dict) -> bool:
    """Whether a model-facing tool name is denied by selection or by policy.

    Both the picker and an approval policy may name a tool by its class name, its
    runtime name or a legacy shell alias, so every spelling is checked. Builtins
    are the floor every agent keeps and are never denied.
    """
    from suzent.tools.names import BUILTIN_TOOL_NAMES, policy_alias_names
    from suzent.tools.registry import get_tool_class_name

    class_name = get_tool_class_name(runtime_name)
    if class_name in BUILTIN_TOOL_NAMES:
        return False
    names = {*policy_alias_names(runtime_name), class_name} - {None}
    return bool(names & denied_names) or any(
        policy.get(name) == "always_deny" for name in names
    )


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
