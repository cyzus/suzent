"""
SpawnSubagentTool: delegate a long-running task to an isolated background agent.

The spawned sub-agent runs independently with a restricted tool whitelist.
The parent agent receives an immediate confirmation and continues responding
to the user. The sub-agent's completion is pushed back as a
[System Notification] in the parent chat.
"""

from typing import Optional

from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolGroup


class SpawnSubagentTool(Tool):
    """Spawn a background sub-agent to handle a long-running task."""

    name: str = "SpawnSubagentTool"
    tool_name: str = "spawn_subagent"
    group: ToolGroup = ToolGroup.AGENT

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        description: str,
        tools_allowed: list[str],
        model_override: Optional[str] = None,
    ) -> str:
        """
        Spawn an isolated background sub-agent for a long-running task.

        The sub-agent runs independently — you do NOT need to wait for it.
        Its result will be delivered as a [System Notification] in this chat.

        Args:
            ctx: The pydantic-ai run context with agent dependencies.
            description: A detailed task prompt for the sub-agent to execute.
            tools_allowed: List of tool registry names the sub-agent is permitted
                to use. Both class-name format (e.g. "BashTool") and function-name
                format (e.g. "bash_execute") are accepted and auto-resolved.
            model_override: Optional model name to use for the sub-agent.
                Defaults to the current model if not specified.
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
        )

        tool_list = ", ".join(resolved) if resolved else "(none)"
        warning = (
            f"\n⚠ Unrecognized tool names ignored: {unrecognized}. "
            f"Use class-name or function-name format; call list_available_tools() to see valid names."
            if unrecognized
            else ""
        )
        return (
            f"✓ Sub-agent spawned (ID: `{task.task_id}`)\n"
            f"Task: {description[:200]}\n"
            f"Tools: {tool_list}"
            f"{warning}\n\n"
            f"The sub-agent is running in the background. "
            f"You will receive a [System Notification] when it completes."
        )
