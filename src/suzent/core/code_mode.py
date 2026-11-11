"""Code mode: the model batches read-only tool calls in one Python snippet.

Built on pydantic-ai-harness ``CodeMode``. The model gets a ``run_code`` tool
whose snippet calls the tools below as async functions, in Monty's sandbox.
Only read-only tools that never ask for approval are offered: Suzent approves
a call by ending the run and resuming it, which a running snippet cannot do,
and a shell inside the sandbox would make the sandbox meaningless.

Calls made from inside a snippet never reach the run's event stream, so
``CodeModeEventsCapability`` reports each one to the chat as an ordinary tool
call while it runs.
"""

import json
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from ag_ui.core import (
    CustomEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import WrapToolExecuteHandler
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.ui.ag_ui._event_stream import _tool_return_content

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger

logger = get_logger(__name__)

RUN_CODE_TOOL = "run_code"

# Read-only, never approval-gated, and useful in a loop. Writes, the shell,
# sub-agents, questions to the user and tools that return images stay native.
CODE_MODE_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "glob_search",
        "grep_search",
        "web_search",
        "webpage_fetch",
        "memory_search",
        "session_search",
        "list_tasks",
        "agent_list",
        "agent_read",
        "check_video",
        "mail_search",
        "mail_read",
    }
)

# A snippet's own execution is bounded by Monty (30s, not counting time spent
# in tools), but each tool it calls can take up to its own timeout, one after
# another. The stream waits this long for the run_code result.
RUN_CODE_STREAM_TIMEOUT_SECONDS = 600.0


def _sandboxed(ctx: RunContext[AgentDeps], tool_def: ToolDefinition) -> bool:
    return tool_def.name in CODE_MODE_TOOLS


def build_code_mode() -> AbstractCapability[AgentDeps]:
    """The CodeMode capability, offering only ``CODE_MODE_TOOLS`` to snippets."""
    from pydantic_ai_harness import CodeMode

    return CodeMode(tools=_sandboxed)


def parent_call_id(tool_call_id: str) -> str | None:
    """The run_code call a snippet's nested call id belongs to."""
    parent, separator, index = tool_call_id.rpartition("__")
    return parent if separator and index.isdigit() else None


@dataclass
class CodeModeEventsCapability(AbstractCapability[AgentDeps]):
    """Show the tools a run_code snippet calls as they start and finish.

    The events go to ``deps.ui_event_queue``, which the stream drains on its
    own schedule, so they arrive while run_code is still running. They are
    the same AG-UI events a direct call produces, so the chat renders and
    persists them like any other tool call. A ``code_mode_call`` event links
    each one to its run_code call.
    """

    _active_runs: set[str] = field(default_factory=set)

    async def wrap_tool_execute(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: Any,
        handler: WrapToolExecuteHandler,
    ) -> Any:
        if call.tool_name == RUN_CODE_TOOL:
            self._active_runs.add(call.tool_call_id)
            try:
                return await handler(args)
            finally:
                self._active_runs.discard(call.tool_call_id)

        parent = parent_call_id(call.tool_call_id)
        queue = getattr(ctx.deps, "ui_event_queue", None)
        if parent not in self._active_runs or queue is None:
            return await handler(args)

        await queue.put(
            CustomEvent(
                name="code_mode_call",
                value={"toolCallId": call.tool_call_id, "parentToolCallId": parent},
            )
        )
        await queue.put(
            ToolCallStartEvent(
                tool_call_id=call.tool_call_id, tool_call_name=call.tool_name
            )
        )
        await queue.put(
            ToolCallArgsEvent(
                tool_call_id=call.tool_call_id,
                delta=json.dumps(args, ensure_ascii=False, default=str),
            )
        )
        await queue.put(ToolCallEndEvent(tool_call_id=call.tool_call_id))
        try:
            result = await handler(args)
        except Exception as error:
            await queue.put(
                ToolCallResultEvent(
                    message_id=str(uuid4()),
                    tool_call_id=call.tool_call_id,
                    content=f"{type(error).__name__}: {error}",
                    role="tool",
                )
            )
            await queue.put(
                CustomEvent(
                    name="tool_call_outcome",
                    value={"toolCallId": call.tool_call_id, "outcome": "failed"},
                )
            )
            raise
        part = ToolReturnPart(
            tool_name=call.tool_name, content=result, tool_call_id=call.tool_call_id
        )
        await queue.put(
            ToolCallResultEvent(
                message_id=str(uuid4()),
                tool_call_id=call.tool_call_id,
                content=_tool_return_content(part),
                role="tool",
            )
        )
        return result


def nested_calls(return_part: Any) -> list[tuple[Any, Any]]:
    """The (call, return) pairs a stored run_code return recorded, in call order.

    Reads both live parts and the dicts a reloaded history holds. A call that
    failed has no return.
    """
    metadata = getattr(return_part, "metadata", None)
    if not isinstance(metadata, dict):
        return []
    calls = metadata.get("tool_calls")
    returns = metadata.get("tool_returns") or {}
    if not isinstance(calls, dict) or not isinstance(returns, dict):
        return []
    return [(call, returns.get(call_id)) for call_id, call in calls.items()]


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def code_mode_display_part(
    call: Any,
    tool_return: Any,
    *,
    parent_id: str,
    format_args: Callable[[str, str], str],
    format_output: Callable[[Any], str],
) -> dict[str, Any]:
    """The chat's tool part for one call a snippet made, as the stream showed it."""
    tool_name = str(_field(call, "tool_name") or "")
    args = _field(call, "args")
    args_text = (
        args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)
    )
    display: dict[str, Any] = {
        "type": "tool",
        "toolCallId": str(_field(call, "tool_call_id") or ""),
        "toolName": tool_name,
        "args": format_args(tool_name, args_text),
        "state": "completed",
        "parentToolCallId": parent_id,
    }
    if tool_return is None:
        display["outcome"] = "failed"
    else:
        display["output"] = format_output(_field(tool_return, "content"))
    return display
