"""The memory_search tool is a sidebar-toggleable equipment tool, decoupled from the
global memory toggle. memory_enabled now governs only memory context injection.
"""

from unittest.mock import MagicMock, patch

import suzent.agent_manager as am


def _equipped_tool_names(config):
    """Return the tool_name of every function equipped on the agent for *config*."""
    captured = {}

    def fake_agent(model, **kwargs):
        captured["tools"] = kwargs.get("tools") or []
        return MagicMock()

    with (
        patch.object(am, "create_pydantic_ai_model", return_value=MagicMock()),
        patch.object(am, "Agent", fake_agent),
    ):
        am.create_agent(config)

    return {getattr(fn, "__name__", None) for fn in captured["tools"]}


def test_memory_search_equipped_when_in_tools_even_if_memory_disabled():
    names = _equipped_tool_names(
        {"tools": ["ReadFileTool", "MemorySearchTool"], "memory_enabled": False}
    )
    assert "memory_search" in names


def test_memory_search_absent_when_not_in_tools_even_if_memory_enabled():
    names = _equipped_tool_names({"tools": ["ReadFileTool"], "memory_enabled": True})
    assert "memory_search" not in names


def test_session_search_equipped_when_in_tools():
    names = _equipped_tool_names(
        {"tools": ["ReadFileTool", "SessionSearchTool"], "memory_enabled": False}
    )
    assert "session_search" in names


def test_memory_and_recall_tools_are_activatable_via_tool_search():
    """Both recall tools are deferrable, so tool_search can activate them mid-session
    when they aren't already equipped."""
    from suzent.tools.tool_search_tool import TOOL_CATALOG

    assert "MemorySearchTool" in TOOL_CATALOG
    assert "SessionSearchTool" in TOOL_CATALOG
