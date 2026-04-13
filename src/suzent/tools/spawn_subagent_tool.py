"""
SpawnSubagentTool: delegate a task to an isolated sub-agent.

Supports two execution modes:
- run_in_background=True (default): fire-and-forget; parent continues immediately.
  Completion is pushed back as a [System Notification] and automatically triggers
  a parent LLM wakeup turn.
- run_in_background=False: blocking; parent awaits the child's result and receives
  it as a direct tool_result, enabling sequential multi-agent pipelines.

The cwd parameter lets you pin the sub-agent's bash working directory to a
specific path (e.g. a build folder or git worktree).
"""

from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult


class SpawnSubagentTool(Tool):
    """Spawn a sub-agent to handle a task, either blocking or in the background."""

    name: str = "SpawnSubagentTool"
    tool_name: str = "spawn_subagent"
    group: ToolGroup = ToolGroup.AGENT

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        description: Annotated[
            str, Field(description="Detailed task prompt for the sub-agent to execute.")
        ],
        tools_allowed: Annotated[
            list[str],
            Field(
                description=(
                    "List of tool registry names the sub-agent may use. Prefer exact class-name keys like 'BashTool'."
                )
            ),
        ],
        run_in_background: Annotated[
            bool,
            Field(
                description=(
                    "If true, the sub-agent runs in the background and returns a task ID immediately."
                )
            ),
        ] = True,
        cwd: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional absolute working directory for bash commands inside the sub-agent.",
            ),
        ] = None,
        model_override: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Optional model name to use for the sub-agent.",
            ),
        ] = None,
    ) -> ToolResult:
        """
        Spawn an isolated sub-agent for a task.

        Args:
            ctx: The pydantic-ai run context with agent dependencies.
            description: A detailed task prompt for the sub-agent to execute.
            tools_allowed: List of tool registry names the sub-agent may use.
                Both class-name (e.g. "BashTool") and function-name
                (e.g. "bash_execute") formats are accepted.
            run_in_background: If True (default), fire-and-forget — you receive
                an immediate confirmation and a [System Notification] + automatic
                wakeup when the sub-agent finishes. If False, this call blocks
                until the sub-agent completes and returns its result directly.
            cwd: Optional absolute path to use as the working directory for bash
                commands inside the sub-agent (e.g. a build folder or worktree).
                Defaults to the standard per-session directory.
            model_override: Optional model name for the sub-agent.
        """
        from suzent.core.subagent_runner import spawn_subagent, _resolve_tool_names

        parent_chat_id = ctx.deps.chat_id

        if not parent_chat_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "No chat context is available for sub-agent spawning.",
            )

        if not description.strip():
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "description is required.",
            )

        # Validate tool names before spawning so errors surface immediately
        resolved, unrecognized = _resolve_tool_names(tools_allowed)
        if tools_allowed and not resolved:
            from suzent.tools.registry import list_available_tools

            available = ", ".join(list_available_tools())
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "None of the provided tool names were recognized.",
                metadata={
                    "unrecognized_tools": unrecognized,
                    "available_tools": available,
                },
            )

        task = await spawn_subagent(
            parent_chat_id=parent_chat_id,
            description=description,
            tools_allowed=tools_allowed,
            model_override=model_override,
            run_in_background=run_in_background,
            cwd=cwd,
        )

        tool_list = ", ".join(resolved) if resolved else "(none)"
        metadata = {
            "task_id": task.task_id,
            "chat_id": task.chat_id,
            "parent_chat_id": task.parent_chat_id,
            "status": task.status,
            "tools_allowed": task.tools_allowed,
            "resolved_tools": resolved,
            "unrecognized_tools": unrecognized,
            "cwd": cwd,
            "model_override": model_override,
            "run_in_background": run_in_background,
        }

        if not run_in_background:
            # Blocking mode: return the actual result so the parent LLM can act on it
            if task.status == "completed":
                return ToolResult.success_result(
                    f"Sub-agent {task.task_id} completed.\nTask: {description[:200]}\nTools: {tool_list}",
                    metadata={**metadata, "result_summary": task.result_summary},
                )
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Sub-agent {task.task_id} failed.",
                metadata={**metadata, "error": task.error},
            )

        # Background mode: return spawn confirmation
        return ToolResult.success_result(
            (
                f"Sub-agent spawned (ID: {task.task_id}).\n"
                f"Task: {description[:200]}\n"
                f"Tools: {tool_list}"
            ),
            metadata=metadata,
        )
