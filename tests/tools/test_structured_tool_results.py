"""Results that calling code can use without parsing the message text.

Code mode hands a tool's result to model-written Python, which can only rely
on what the return type declares. Each tool here keeps its message for the
model and adds the same data as typed metadata, hidden from the model by
``model_excluded_metadata`` so a native call does not pay for it twice.
"""

import json
from types import SimpleNamespace

import pytest
from pydantic_ai import Tool as PydanticTool
from pydantic_ai.messages import ToolReturnPart

from suzent.core.context_compressor import estimate_history_tokens
from suzent.tools.base import ToolResult
from suzent.tools.capability import without_model_excluded_metadata
from suzent.tools.filesystem.glob_tool import GlobTool
from suzent.tools.filesystem.grep_tool import GrepTool
from suzent.tools.recall.memory_tools import MemorySearchTool
from suzent.tools.registry import _all_tool_classes, _make_tool
from suzent.tools.tasks.task_list_tool import _task_record
from suzent.tools.websearch_tool import _with_structured_results

STRUCTURED_TOOLS = {
    "glob_search": {"matches"},
    "grep_search": {"matches"},
    "read_file": {"total_lines", "start_line", "end_line", "truncated"},
    "web_search": {"results"},
    "webpage_fetch": {"title", "source_id"},
    "memory_search": {"memories"},
    "session_search": {"sessions", "messages"},
    "list_tasks": {"tasks"},
}


def _return_schemas() -> dict[str, dict]:
    schemas = {}
    for cls in _all_tool_classes():
        if cls.tool_name in STRUCTURED_TOOLS:
            built = _make_tool(cls)
            tool = built if isinstance(built, PydanticTool) else PydanticTool(built)
            schemas[cls.tool_name] = tool.tool_def.return_schema
    return schemas


def _metadata_properties(schema: dict) -> set[str]:
    ref = schema["properties"]["metadata"]["$ref"].rsplit("/", 1)[-1]
    return set(schema["$defs"][ref]["properties"])


@pytest.mark.parametrize("tool_name", sorted(STRUCTURED_TOOLS))
def test_return_type_declares_the_structured_metadata(tool_name):
    schema = _return_schemas()[tool_name]

    assert STRUCTURED_TOOLS[tool_name] <= _metadata_properties(schema)


@pytest.mark.parametrize(
    "cls",
    [cls for cls in _all_tool_classes() if cls.tool_name in STRUCTURED_TOOLS],
    ids=lambda cls: cls.tool_name,
)
def test_hidden_metadata_is_declared(cls):
    schema = _return_schemas()[cls.tool_name]

    assert cls.model_excluded_metadata <= _metadata_properties(schema)


class _Resolver:
    sandbox_enabled = False

    def __init__(self, files):
        self._files = files

    def find_files(self, pattern, path):
        return self._files


def _ctx(tmp_path, resolver):
    return SimpleNamespace(
        deps=SimpleNamespace(
            chat_id="chat-1",
            sandbox_enabled=False,
            custom_volumes=[],
            workspace_root=str(tmp_path),
            path_resolver=resolver,
        )
    )


def test_glob_lists_every_match_past_the_message_cap(tmp_path, monkeypatch):
    files = []
    for index in range(120):
        path = tmp_path / f"f_{index:03}.py"
        path.write_text("", encoding="utf-8")
        files.append((path, str(path)))
    resolver = _Resolver(files)
    monkeypatch.setattr(
        "suzent.tools.filesystem.glob_tool.get_or_create_path_resolver",
        lambda deps: resolver,
    )

    result = GlobTool().forward(_ctx(tmp_path, resolver), pattern="*.py")

    assert "... and 20 more" in result.message
    assert len(result.metadata["matches"]) == 120
    assert result.metadata["matches"][0] == {"path": str(files[0][0]), "is_dir": False}
    assert result.metadata["matches_truncated"] is False


def test_grep_matches_drop_context_markers(tmp_path, monkeypatch):
    source = tmp_path / "example.py"
    source.write_text("before\nneedle\nafter\n", encoding="utf-8")
    resolver = _Resolver([(source, str(source))])
    monkeypatch.setattr(
        "suzent.tools.filesystem.grep_tool.get_or_create_path_resolver",
        lambda deps: resolver,
    )
    tool = GrepTool()
    monkeypatch.setattr(tool, "_ripgrep_checked", True)
    monkeypatch.setattr(tool, "_ripgrep_path", None)

    result = tool.forward(
        _ctx(tmp_path, resolver), pattern="needle", path=str(tmp_path), context_lines=1
    )

    assert result.metadata["matches"] == [
        {"path": str(source), "line": 1, "text": "before", "is_match": False},
        {"path": str(source), "line": 2, "text": "needle", "is_match": True},
        {"path": str(source), "line": 3, "text": "after", "is_match": False},
    ]


def test_web_search_copies_the_json_results_into_metadata():
    hit = {"title": "Suzent", "url": "https://suzent.com", "description": "Agent"}
    raw = ToolResult.success_result(
        json.dumps({"source": "DDGS", "query": "suzent", "results": [hit]}),
        metadata={"source": "DDGS", "query": "suzent", "result_count": 1},
    )

    result = _with_structured_results(raw)

    assert result.metadata["results"] == [hit]
    assert result.message == raw.message


async def test_memory_search_lists_each_memory():
    class _Manager:
        async def search_memories(self, query, limit, chat_id, user_id, kinds=None):
            return [
                {
                    "content": "prefers tea",
                    "created_at": "2026-11-01T10:00:00",
                    "metadata": {"tags": ["drink"], "kind": "user"},
                    "score": 0.8,
                    "importance": 0.5,
                }
            ]

    ctx = SimpleNamespace(deps=SimpleNamespace(memory_manager=_Manager(), user_id="u"))

    result = await MemorySearchTool().forward(ctx, query="tea")

    assert result.metadata["memories"] == [
        {
            "content": "prefers tea",
            "stored": "2026-11-01",
            "relevance": 0.8,
            "importance": 0.5,
            "tags": ["drink"],
            "kind": "user",
        }
    ]


def test_task_record_carries_the_id_update_task_takes():
    task = SimpleNamespace(
        id=7,
        title="Ship",
        description="Ship it",
        status="pending",
        assignee=None,
        blocks=[8],
        blocked_by=[],
        active_form=None,
        waiting_kind=None,
        waiting_reason=None,
        next_action=None,
        result_summary=None,
        result_path=None,
    )

    record = _task_record(task)

    assert record["id"] == 7 and record["blocks"] == [8]


def test_hidden_metadata_is_not_counted_as_context():
    matches = [
        {"path": f"/f{i}.py", "line": 1, "text": "x" * 200, "is_match": True}
        for i in range(200)
    ]
    part = ToolReturnPart(
        tool_name="grep_search",
        tool_call_id="g",
        content=ToolResult.success_result(
            "Found 200 matches", metadata={"match_count": 200, "matches": matches}
        ),
    )

    sent = without_model_excluded_metadata(part)

    assert "matches" not in sent.content["metadata"]
    assert part.content.metadata["matches"] == matches
    assert estimate_history_tokens([SimpleNamespace(parts=[part])]) < 100
