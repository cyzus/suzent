"""Tool-name constants and the legacy-selection migrations that use them.

These live apart from :mod:`suzent.tools.registry` because config validation
needs them on every startup, while the registry pulls in pydantic-ai, MCP and
the rest of the agent runtime. Keep this module free of heavy imports.
"""

from __future__ import annotations

from typing import List

SHELL_TOOL_CLASS_NAMES = (
    "RunCommandTool",
    "StartCommandTool",
    "CheckCommandTool",
    "StopCommandTool",
)

AGENT_LIFECYCLE_TOOL_NAMES = (
    "AgentListTool",
    "AgentReadTool",
    "AgentSendTool",
    "AgentStopTool",
)

LEGACY_SHELL_TOOL_NAMES = {
    "ShellTool",
    "BashTool",
    "ProcessTool",
    "bash_execute",
    "process_manage",
}


def migrate_shell_tool_names(tool_names: List[str]) -> List[str]:
    """Expand legacy aggregate shell selections into independently selectable tools."""
    migrated: list[str] = []
    for name in tool_names:
        if name in LEGACY_SHELL_TOOL_NAMES:
            migrated.extend(SHELL_TOOL_CLASS_NAMES)
        else:
            migrated.append(name)
    return list(dict.fromkeys(migrated))


def expand_tool_dependencies(tool_names: List[str]) -> List[str]:
    """Normalize legacy aggregate selections while preserving modern choices."""
    expanded = migrate_shell_tool_names(tool_names)
    if "AgentTool" in expanded:
        expanded.extend(AGENT_LIFECYCLE_TOOL_NAMES)
    return list(dict.fromkeys(expanded))
