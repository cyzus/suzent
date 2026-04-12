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

from typing import Optional

from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolGroup


class SpawnSubagentTool(Tool):
    """Spawn a sub-agent to handle a task, either blocking or in the background."""

    name: str = "SpawnSubagentTool"
    tool_name: str = "spawn_subagent"
    group: ToolGroup = ToolGroup.AGENT

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        description: str,
        tools_allowed: list[str],
        run_in_background: bool = True,
        cwd: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> str:
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

        # Validate tool names before spawning so errors surface immediately
        resolved, unrecognized = _resolve_tool_names(tools_allowed)
        if tools_allowed and not resolved:
            from suzent.tools.registry import list_available_tools

            available = ", ".join(list_available_tools())
            return (
                f"✗ Failed to spawn sub-agent: none of the provided tool names were recognized.\n"
                f"Unrecognized: {unrecognized}\n"
                f"Available tools: {available}\n"
                f"Use class-name keys (e.g. 'BashTool', not 'bash_execute')."
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
        cwd_note = f"\nCWD: `{cwd}`" if cwd else ""
        warning = (
            f"\n⚠ Unrecognized tool names ignored: {unrecognized}. "
            f"Use class-name or function-name format; call list_available_tools() to see valid names."
            if unrecognized
            else ""
        )

        if not run_in_background:
            # Blocking mode: return the actual result so the parent LLM can act on it
            if task.status == "completed":
                return (
                    f"✓ Sub-agent `{task.task_id}` completed.{cwd_note}\n"
                    f"Task: {description[:200]}\n"
                    f"Tools: {tool_list}{warning}\n\n"
                    f"Result:\n{task.result_summary}"
                )
            else:
                return (
                    f"✗ Sub-agent `{task.task_id}` failed.{cwd_note}\n"
                    f"Task: {description[:200]}\n"
                    f"Error: {task.error}"
                )

        # Background mode: return spawn confirmation
        return (
            f"✓ Sub-agent spawned (ID: `{task.task_id}`){cwd_note}\n"
            f"Task: {description[:200]}\n"
            f"Tools: {tool_list}"
            f"{warning}\n\n"
            f"The sub-agent is running in the background. "
            f"You will receive a [System Notification] and an automatic wakeup when it completes."
        )
