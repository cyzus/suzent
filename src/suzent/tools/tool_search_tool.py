"""
ToolSearchTool: meta-tool that lets the agent activate tools it needs mid-conversation.

The catalog is built from _all_tool_classes() at import time and stays in sync
automatically as tools are added to the registry.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Catalog: built once at import time
# ---------------------------------------------------------------------------


def _build_catalog() -> dict[str, str]:
    from suzent.tools.registry import _all_tool_classes

    catalog: dict[str, str] = {}
    for cls in _all_tool_classes():
        if not getattr(cls, "deferrable", True):
            continue
        description = (cls.__doc__ or "").strip().split("\n")[0].strip()
        if not description and cls.session_guidance:
            description = cls.session_guidance.strip().split("\n")[0]
        if not description:
            description = cls.tool_name.replace("_", " ")
        catalog[cls.name] = description
    return catalog


TOOL_CATALOG: dict[str, str] = _build_catalog()


def _build_runtime_name_catalog() -> dict[str, str]:
    from suzent.tools.registry import _all_tool_classes

    return {
        cls.name: cls.tool_name
        for cls in _all_tool_classes()
        if getattr(cls, "deferrable", True)
    }


TOOL_RUNTIME_NAMES: dict[str, str] = _build_runtime_name_catalog()


def _matches_tool_key(query: str, tool_name: str) -> bool:
    query_key = query.strip().casefold()
    runtime_name = TOOL_RUNTIME_NAMES.get(tool_name, "")
    return query_key in {tool_name.casefold(), runtime_name.casefold()}


def _format_tool_keys(tool_name: str) -> str:
    runtime_name = TOOL_RUNTIME_NAMES.get(tool_name, "")
    if runtime_name:
        return f"{tool_name} ({runtime_name})"
    return tool_name


def _is_denied_by_policy(ctx: RunContext[AgentDeps], tool_name: str) -> bool:
    policy = getattr(ctx.deps, "tool_approval_policy", {}) or {}
    runtime_name = TOOL_RUNTIME_NAMES.get(tool_name, "")
    return (
        policy.get(tool_name) == "always_deny"
        or bool(runtime_name)
        and policy.get(runtime_name) == "always_deny"
    )


# ---------------------------------------------------------------------------
# SSE emission helper
# ---------------------------------------------------------------------------


async def _emit_tool_activated(chat_id: str, tool_names: list[str]) -> None:
    if not tool_names:
        return
    from suzent.core.stream_registry import push_custom_event

    await push_custom_event(
        chat_id,
        "tool_activated",
        {"toolNames": tool_names, "chatId": chat_id},
    )


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def _build_status_report(
    base_tool_names: frozenset,
    ai_activated: set,
    catalog: dict[str, str],
) -> str:
    user_selected = [n for n in catalog if n in base_tool_names]
    ai_active = [n for n in catalog if n in ai_activated and n not in base_tool_names]
    available = [
        n for n in catalog if n not in base_tool_names and n not in ai_activated
    ]

    lines: list[str] = []
    if user_selected:
        lines.append("ENABLED (user-selected): " + ", ".join(user_selected))
    if ai_active:
        lines.append("ACTIVE (AI-activated this session): " + ", ".join(ai_active))
    if available:
        lines.append(
            "AVAILABLE TO ACTIVATE:\n"
            + "\n".join(f"  - {_format_tool_keys(n)}: {catalog[n]}" for n in available)
        )
    return "\n\n".join(lines) if lines else "No deferrable tools found."


# ---------------------------------------------------------------------------
# The tool function itself
# ---------------------------------------------------------------------------


async def tool_search(
    ctx: RunContext[AgentDeps],
    query: Annotated[
        Optional[str],
        Field(
            description=(
                "Exact tool key to activate, e.g. 'ImageGenerationTool' or "
                "'generate_image'. Leave empty or omit to list all tools with "
                "their current status."
            )
        ),
    ] = None,
) -> str:
    """
    Search for and activate tools, or list all tools with their current status.

    - With a query: activates the exact matching tool key (available next step).
    - Without a query: shows which tools are user-enabled, AI-activated, and available.
    """
    from suzent.agent_manager import get_unlocked_tools, unlock_tool

    chat_id = ctx.deps.chat_id
    base_tool_names = ctx.deps.base_tool_names
    ai_activated = get_unlocked_tools(chat_id)

    # List mode: no query, just show status
    if not query or not query.strip():
        return _build_status_report(base_tool_names, ai_activated, TOOL_CATALOG)

    # Search catalog for matches not already active (user or AI)
    already_active = base_tool_names | ai_activated
    matched: list[str] = []
    for tool_name, description in TOOL_CATALOG.items():
        if tool_name in already_active or _is_denied_by_policy(ctx, tool_name):
            continue
        if _matches_tool_key(query, tool_name):
            matched.append(tool_name)

    if not matched:
        report = _build_status_report(base_tool_names, ai_activated, TOOL_CATALOG)
        return f"No tools matched '{query}'.\n\n{report}"

    newly_activated: list[str] = []
    for tool_name in matched:
        unlock_tool(chat_id, tool_name)
        newly_activated.append(tool_name)

    await _emit_tool_activated(chat_id, newly_activated)

    names = ", ".join(newly_activated)
    return f"Activated: {names}. These tools are now available in your next step."
