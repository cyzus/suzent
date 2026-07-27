from types import SimpleNamespace

from pydantic_ai.messages import FunctionToolResultEvent, ToolSearchReturnPart
from pydantic_ai.tools import ToolDefinition

from suzent import streaming
from suzent.agent_manager import clear_suppressed_tools, suppress_tool
from suzent.tools.registry import (
    get_deferred_tool_functions,
    get_tool_class_name,
    get_tool_runtime_name,
)


def test_registry_builds_native_deferred_tools() -> None:
    tools = get_deferred_tool_functions({"ReadFileTool"})
    by_name = {tool.name: tool for tool in tools}

    assert "read_file" not in by_name
    assert by_name["memory_search"].defer_loading is True
    assert "use_skill" not in by_name


def test_registry_maps_runtime_and_class_names() -> None:
    assert get_tool_class_name("memory_search") == "MemorySearchTool"
    assert get_tool_runtime_name("MemorySearchTool") == "memory_search"


async def test_suppressed_deferred_tool_is_hidden() -> None:
    chat_id = "native-search-test"
    suppress_tool(chat_id, "MemorySearchTool")
    try:
        tool = next(
            tool
            for tool in get_deferred_tool_functions(set())
            if tool.name == "memory_search"
        )
        definition = ToolDefinition(
            name="memory_search",
            description="Search memory",
            parameters_json_schema={"type": "object", "properties": {}},
        )
        ctx = SimpleNamespace(
            deps=SimpleNamespace(
                chat_id=chat_id,
                base_tool_names=frozenset(),
                tool_approval_policy={},
            )
        )

        assert await tool.prepare(ctx, definition) is None
    finally:
        clear_suppressed_tools(chat_id)


def test_streaming_extracts_native_tool_search_matches() -> None:
    event = FunctionToolResultEvent(
        ToolSearchReturnPart(
            content={"discovered_tools": [{"name": "memory_search"}]},
            tool_call_id="search-1",
        )
    )

    assert streaming._tool_search_class_names(event) == ["MemorySearchTool"]
