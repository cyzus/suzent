"""A run that names its tools gets those tools and no others."""

from unittest.mock import MagicMock, patch

from pydantic_ai import Tool as PydanticTool

import suzent.agent_manager as am
from suzent.tools.names import expand_tool_dependencies


def _tools(config):
    captured = {}

    def fake_agent(model, **kwargs):
        captured["tools"] = kwargs.get("tools") or []
        captured["capabilities"] = kwargs.get("capabilities") or []
        return MagicMock()

    with (
        patch.object(am, "create_pydantic_ai_model", return_value=MagicMock()),
        patch.object(am, "get_enabled_models_from_db", return_value=["test/model"]),
        patch.object(am, "_build_mcp_servers", return_value=[]),
        patch.object(am, "Agent", fake_agent),
    ):
        am.create_agent({"model": "test/model", **config})

    loaded, deferred = set(), set()
    for tool in captured["tools"]:
        name = tool.name if isinstance(tool, PydanticTool) else tool.__name__
        is_deferred = isinstance(tool, PydanticTool) and tool.defer_loading
        (deferred if is_deferred else loaded).add(name)
    for capability in captured["capabilities"]:
        get_toolset = getattr(capability, "get_toolset", None)
        toolset = get_toolset() if get_toolset is not None else None
        if toolset is not None:
            loaded.update(toolset.tools)
    return loaded, deferred


def test_expand_adds_the_builtin_floor_unless_told_not_to():
    assert "SendFileTool" in expand_tool_dependencies(["RunCommandTool"])
    assert expand_tool_dependencies(["RunCommandTool"], with_builtins=False) == [
        "RunCommandTool"
    ]


def test_a_normal_agent_keeps_the_builtin_floor_and_a_searchable_pool():
    loaded, deferred = _tools({"tools": ["ReadFileTool"]})

    assert "send_file" in loaded
    assert deferred


def test_exact_tools_drops_the_floor_and_the_searchable_pool():
    loaded, deferred = _tools(
        {"tools": ["ReadFileTool", "RunCommandTool"], "exact_tools": True}
    )

    assert loaded == {"read_file", "run_command"}
    assert deferred == set()


def test_exact_tools_leaves_mcp_servers_out():
    with patch("suzent.core.mcp_store.as_agent_config") as saved:
        assert am._build_mcp_servers({"exact_tools": True}) == []

    saved.assert_not_called()
