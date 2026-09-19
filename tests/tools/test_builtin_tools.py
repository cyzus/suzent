"""The floor under tool selection: builtins cannot be turned off.

``Tool.builtin`` is the source of truth; ``names.BUILTIN_TOOL_NAMES`` is the
import-light copy that config validation and the agent builder read without
pulling in pydantic-ai. These tests keep the two in step and prove the floor
survives an empty selection.
"""

from suzent.tools.names import BUILTIN_TOOL_NAMES, expand_tool_dependencies
from suzent.tools.registry import get_builtin_tool_names, get_tool_capabilities


def test_constant_matches_the_classes_that_declare_builtin() -> None:
    assert sorted(BUILTIN_TOOL_NAMES) == sorted(get_builtin_tool_names())


def test_an_empty_selection_still_gets_the_builtins() -> None:
    assert sorted(expand_tool_dependencies([])) == sorted(BUILTIN_TOOL_NAMES)


def test_a_selection_that_drops_a_builtin_gets_it_back() -> None:
    """Saved preferences, ACP, A2A and sub-agent configs all pass through here,
    so this is the one place the floor has to hold."""
    selected = expand_tool_dependencies(["WebSearchTool", "WriteFileTool"])

    assert set(BUILTIN_TOOL_NAMES).issubset(selected)
    # The floor adds, it never reorders or drops what the caller chose.
    assert selected[:2] == ["WebSearchTool", "WriteFileTool"]


def test_expansion_stays_idempotent() -> None:
    once = expand_tool_dependencies(["AgentTool"])

    assert expand_tool_dependencies(once) == once


def test_every_builtin_is_visible_in_the_catalog() -> None:
    """A locked tool the picker cannot render is worse than an unlocked one: the
    agent holds it and the user has no way to see that."""
    catalog_ids = {
        tool["id"]
        for capability in get_tool_capabilities()
        for tool in capability["tools"]
    }
    flagged = {
        tool["id"]
        for capability in get_tool_capabilities()
        for tool in capability["tools"]
        if tool["builtin"]
    }

    assert set(BUILTIN_TOOL_NAMES).issubset(catalog_ids)
    assert flagged == set(BUILTIN_TOOL_NAMES)
