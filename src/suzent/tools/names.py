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

# Tools the user cannot turn off. Every agent gets these, whatever the saved
# selection says, so a stripped-down config can still read the workspace, load a
# skill and ask the user a question. Mirrors ``Tool.builtin`` -- the registry
# owns the flag, this tuple is the import-light copy config validation and the
# agent builder read; ``test_builtin_tools`` keeps the two in step.
BUILTIN_TOOL_NAMES = (
    "ReadFileTool",
    "GlobTool",
    "GrepTool",
    "SkillTool",
    "AskQuestionTool",
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


# Every name an approval policy may have stored for a given runtime tool. A
# policy written before the aggregate shell tool was split still says
# "ShellTool", and the picker writes class names while the model calls runtime
# names, so a denial has to be looked up under all of them.
#
# This lives here rather than on ``Tool`` so the base class does not have to
# know which concrete tools exist; ``names`` is already the import-light home
# for shell-tool aliasing.
POLICY_TOOL_ALIASES = {
    "run_command": ("RunCommandTool", "ShellTool"),
    "start_command": ("StartCommandTool", "ShellTool"),
    "check_command": ("CheckCommandTool",),
    "stop_command": ("StopCommandTool",),
}


def policy_alias_names(tool_name: str) -> List[str]:
    """Names an approval policy could have stored for *tool_name*, itself first."""
    return [tool_name, *POLICY_TOOL_ALIASES.get(tool_name, ())]


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
    # The floor goes last so it also covers callers that never touch the picker
    # -- ACP, A2A and sub-agent configs build their tool lists directly.
    expanded.extend(BUILTIN_TOOL_NAMES)
    return list(dict.fromkeys(expanded))
