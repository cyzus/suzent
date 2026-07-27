"""The memory_search tool is a sidebar-toggleable equipment tool, decoupled from the
global memory toggle. memory_enabled now governs only memory context injection.
"""

from unittest.mock import MagicMock, patch

from pydantic_ai import Tool as PydanticTool

import suzent.agent_manager as am


def _tool_names(config, *, deferred):
    """Return model-facing tool names with the requested loading mode."""
    captured = {}

    def fake_agent(model, **kwargs):
        captured["tools"] = kwargs.get("tools") or []
        return MagicMock()

    with (
        patch.object(am, "create_pydantic_ai_model", return_value=MagicMock()),
        patch.object(am, "get_enabled_models_from_db", return_value=["test/model"]),
        patch.object(am, "_build_mcp_servers", return_value=[]),
        patch.object(
            am,
            "get_skill_manager",
            return_value=MagicMock(enabled_skills=set()),
        ),
        patch.object(am, "Agent", fake_agent),
    ):
        am.create_agent({"model": "test/model", **config})

    names = set()
    for tool in captured["tools"]:
        is_deferred = isinstance(tool, PydanticTool) and tool.defer_loading
        if is_deferred != deferred:
            continue
        names.add(tool.name if isinstance(tool, PydanticTool) else tool.__name__)
    return names


def test_memory_search_equipped_when_in_tools_even_if_memory_disabled():
    names = _tool_names(
        {"tools": ["ReadFileTool", "MemorySearchTool"], "memory_enabled": False},
        deferred=False,
    )
    assert "memory_search" in names


def test_memory_search_absent_when_not_in_tools_even_if_memory_enabled():
    names = _tool_names(
        {"tools": ["ReadFileTool"], "memory_enabled": True}, deferred=False
    )
    assert "memory_search" not in names


def test_session_search_equipped_when_in_tools():
    names = _tool_names(
        {"tools": ["ReadFileTool", "SessionSearchTool"], "memory_enabled": False},
        deferred=False,
    )
    assert "session_search" in names


def test_memory_and_recall_tools_use_native_deferred_loading():
    names = _tool_names(
        {"tools": ["ReadFileTool"], "memory_enabled": False}, deferred=True
    )

    assert "memory_search" in names
    assert "session_search" in names
