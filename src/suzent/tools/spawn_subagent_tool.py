"""
SpawnSubagentTool: delegate a task to an isolated sub-agent.

Supports two execution modes:
- run_in_background=True (default): fire-and-forget; parent continues immediately.
  Completion is pushed back as a [System Notification] and automatically triggers
  a parent LLM wakeup turn.
- run_in_background=False: blocking; parent awaits the child's result and receives
  it as a direct tool_result, enabling sequential multi-agent pipelines.

Tool selection supports three mutually exclusive modes:
- subagent_type: use a pre-defined profile that auto-populates the tool list
- tools_allowed: explicit whitelist (can be combined with subagent_type)
- tools_denied: denylist — start from all available tools, subtract listed ones

SpawnSubagentTool is always stripped from the sub-agent's tool set to prevent
recursive spawning, regardless of which selection mode is used.

The cwd parameter lets you pin the sub-agent's bash working directory to a
specific path (e.g. a build folder or git worktree).
"""

from typing import Annotated, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

# ─── Pre-defined subagent profiles ───────────────────────────────────────────

_SUBAGENT_PROFILES: dict[str, list[str]] = {
    "explore": ["GlobTool", "GrepTool", "ReadFileTool"],
    "plan": ["GlobTool", "GrepTool", "ReadFileTool", "WebSearchTool", "WebpageTool"],
    "write": ["ReadFileTool", "WriteFileTool", "EditFileTool", "GlobTool", "GrepTool"],
    "verify": ["BashTool"],
    "web": ["WebSearchTool", "WebpageTool"],
}


class SpawnSubagentTool(Tool):
    """Spawn a sub-agent to handle a task, either blocking or in the background."""

    name: str = "SpawnSubagentTool"
    tool_name: str = "spawn_subagent"
    group: ToolGroup = ToolGroup.AGENT
    guidance_priority: int = 10

    session_guidance: str = (
        "## SpawnSubagentTool — When and How to Delegate\n"
        "\n"
        "### When to spawn a sub-agent (use proactively)\n"
        "- **explore**: when you need to find files by pattern, search code for keywords, or answer "
        "questions about a codebase — especially when a simple search might take more than 3 tries. "
        "Keeps raw search output out of your context window.\n"
        "- **plan**: when a task requires designing an implementation strategy, identifying critical "
        "files, or weighing architectural trade-offs before writing any code.\n"
        "- **write**: when file editing work is independent of your current turn and can run in "
        "parallel (run_in_background=True), or when you want changes isolated in a worktree.\n"
        "- **verify**: REQUIRED after non-trivial code changes (3+ file edits, backend/API changes, "
        "or any logic modification). Spawn BEFORE reporting completion to the user.\n"
        "- **web**: when you need external information that would clutter your context with raw results.\n"
        "- **general (no subagent_type)**: for any complex multi-step task where the raw tool output "
        "would fill your context with content you won't need again.\n"
        "\n"
        "### Parallelism — your most powerful lever\n"
        "Independent sub-agents can run simultaneously. When multiple research angles or tasks "
        "don't depend on each other, spawn them all in the SAME turn with run_in_background=True. "
        "You will be notified as each one finishes.\n"
        "\n"
        "### Tool selection\n"
        "1. **subagent_type** (easiest): use a preset profile (explore / plan / write / verify / web)\n"
        "2. **tools_allowed**: explicit whitelist of tool class names\n"
        "3. **tools_denied**: start from all tools, remove dangerous ones — best for broad agents\n"
        "\n"
        "### Rule — Never delegate understanding\n"
        "Write the description as if briefing a smart colleague who has zero context: include "
        "absolute file paths, exact search terms, expected output format, and acceptance criteria. "
        "Never write 'fix this' or 'based on your findings' — own the synthesis yourself.\n"
    )

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        description: Annotated[
            str, Field(description="Detailed task prompt for the sub-agent to execute.")
        ],
        subagent_type: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "Pre-defined agent profile. Auto-populates tools_allowed. "
                    "Available: 'explore' (read-only code search), 'plan' (read + web research), "
                    "'write' (file editing), 'verify' (bash test/build runner), 'web' (web research). "
                    "Can be combined with tools_allowed (merged) but not with tools_denied."
                ),
            ),
        ] = None,
        tools_allowed: Annotated[
            Optional[list[str]],
            Field(
                default=None,
                description=(
                    "Explicit whitelist of tool class names the sub-agent may use "
                    "(e.g. ['BashTool', 'ReadFileTool']). "
                    "If subagent_type is also set, these are merged with the profile's tools. "
                    "Mutually exclusive with tools_denied."
                ),
            ),
        ] = None,
        tools_denied: Annotated[
            Optional[list[str]],
            Field(
                default=None,
                description=(
                    "Denylist path: start from all available tools, remove these. "
                    "Use for broad agents where you only need to block a few dangerous tools "
                    "(e.g. ['WriteFileTool', 'EditFileTool', 'BashTool'] gives safe read-only access). "
                    "Mutually exclusive with tools_allowed."
                ),
            ),
        ] = None,
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
        inherit_context: Annotated[
            bool,
            Field(
                default=False,
                description=(
                    "If true, the sub-agent receives a snapshot of the current conversation "
                    "history as context. Use when the task requires understanding earlier decisions "
                    "made in this session. Note: inheriting large contexts increases token usage."
                ),
            ),
        ] = False,
        isolation: Annotated[
            Literal["none", "worktree"],
            Field(
                default="none",
                description=(
                    "'none': sub-agent shares the parent filesystem (default). "
                    "'worktree': creates a fresh git worktree on a new branch so changes "
                    "are isolated and can be reviewed or discarded after the task completes."
                ),
            ),
        ] = "none",
        isolation_target_path: Annotated[
            Optional[str],
            Field(
                default=None,
                description=(
                    "Absolute path to the Git repository root to create the worktree in. "
                    "Required when isolation='worktree'. Must be a valid git repository with at least one commit."
                ),
            ),
        ] = None,
    ) -> ToolResult:
        """
        Launch a sub-agent to handle a task autonomously.

        Sub-agents are valuable for two reasons:
        1. **Parallelism** — run independent tasks simultaneously instead of serially.
           Spawn multiple agents in the same turn with run_in_background=True.
        2. **Context protection** — raw tool output (search results, file reads, build logs)
           stays in the sub-agent's context, not yours. Use when a task would otherwise
           fill your window with content you won't need again.

        Available subagent_type profiles and when to use them:
        - 'explore': find files by pattern, search code for keywords, answer codebase questions.
          Use when a direct search might take more than 3 tries or produce large raw output.
        - 'plan': design implementation strategy, identify critical files, weigh trade-offs.
          Use before writing code on any non-trivial task.
        - 'write': edit files. Use with run_in_background=True for parallel independent changes,
          or with isolation='worktree' to sandbox risky edits.
        - 'verify': run tests/build/lint and attempt to break the code. REQUIRED before
          reporting completion on any non-trivial code change (3+ files or logic changes).
        - 'web': web research. Use to keep raw search results out of your context.

        When the agent is done, its result is returned to you — not shown directly to the user.
        Summarize findings in your own words when reporting back.

        Args:
            ctx: The pydantic-ai run context with agent dependencies.
            description: Full task brief. Include file paths, search terms, acceptance criteria.
                The sub-agent has no access to this conversation — be explicit.
            subagent_type: Pre-defined profile. Auto-populates tool list.
            tools_allowed: Explicit whitelist. Merged with subagent_type if both given.
            tools_denied: Denylist — start from all tools, remove these. Mutually exclusive with tools_allowed.
            run_in_background: True (default) = fire-and-forget, auto-wakeup on completion.
                False = blocking, result returned inline.
            cwd: Working directory for bash commands inside the sub-agent.
            model_override: Optional model name for the sub-agent.
            inherit_context: If True, sub-agent receives a snapshot of current conversation history.
            isolation: 'none' (default) or 'worktree' (git-isolated branch).
            isolation_target_path: Git repo root. Required when isolation='worktree'.
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

        # ── Validate isolation params ─────────────────────────────────────────
        if isolation == "worktree" and not isolation_target_path:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "isolation_target_path is required when isolation='worktree'.",
            )

        # ── Resolve effective tool list ───────────────────────────────────────
        if tools_allowed and tools_denied:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "tools_allowed and tools_denied are mutually exclusive. Use one or the other.",
            )

        if tools_denied is not None:
            # Denylist path: start from all available tools, subtract denied
            from suzent.tools.registry import list_available_tools

            all_tools = list_available_tools()
            denied_set = set(tools_denied)
            effective_tools = [t for t in all_tools if t not in denied_set]
        elif subagent_type is not None or tools_allowed is not None:
            # Whitelist path
            effective_tools = list(tools_allowed or [])
            if subagent_type is not None:
                profile_tools = _SUBAGENT_PROFILES.get(subagent_type)
                if profile_tools is None:
                    return ToolResult.error_result(
                        ToolErrorCode.INVALID_ARGUMENT,
                        f"Unknown subagent_type '{subagent_type}'. "
                        f"Available: {', '.join(sorted(_SUBAGENT_PROFILES))}",
                    )
                for t in profile_tools:
                    if t not in effective_tools:
                        effective_tools.append(t)
        else:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Specify subagent_type, tools_allowed, or tools_denied to define the sub-agent's capabilities.",
            )

        # ── Validate tool names before spawning ───────────────────────────────
        resolved, unrecognized = _resolve_tool_names(effective_tools)
        if effective_tools and not resolved:
            from suzent.tools.registry import list_available_tools as _list

            available = ", ".join(_list())
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
            tools_allowed=effective_tools,
            model_override=model_override,
            run_in_background=run_in_background,
            cwd=cwd,
            inherit_context=inherit_context,
            isolation=isolation,
            isolation_target_path=isolation_target_path,
        )

        tool_list = ", ".join(resolved) if resolved else "(none)"
        metadata = {
            "task_id": task.task_id,
            "chat_id": task.chat_id,
            "parent_chat_id": task.parent_chat_id,
            "status": task.status,
            "subagent_type": subagent_type,
            "tools_allowed": task.tools_allowed,
            "resolved_tools": resolved,
            "unrecognized_tools": unrecognized,
            "cwd": cwd,
            "model_override": model_override,
            "run_in_background": run_in_background,
            "inherit_context": inherit_context,
            "isolation": isolation,
            "isolation_target_path": isolation_target_path,
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
