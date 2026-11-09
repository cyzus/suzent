"""Code mode: snippets call read-only tools, and the chat sees each call live."""

import asyncio
import json
from types import SimpleNamespace

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from suzent.core.chat_processor import _rebuild_display_messages
from suzent.core.code_mode import (
    CODE_MODE_TOOLS,
    RUN_CODE_STREAM_TIMEOUT_SECONDS,
    CodeModeEventsCapability,
    build_code_mode,
    parent_call_id,
)
from suzent.streaming import _DraftDisplayAccumulator, _tool_timeout_from_event

SNIPPET = (
    "import asyncio\n"
    'files, hits = await asyncio.gather(glob_search(pattern="*.py"), '
    'web_search(query="suzent"))\n'
    '[files["matches"], hits["results"]]'
)


def glob_search(pattern: str) -> dict:
    """Find files matching a pattern."""
    return {"matches": [f"a{pattern[1:]}"]}


def web_search(query: str) -> dict:
    """Search the web."""
    return {"results": [query]}


def write_file(path: str, content: str) -> str:
    """Write a file."""
    return "written"


def _agent(offered: list[list[str]]) -> Agent:
    async def respond(messages, info: AgentInfo):
        offered.append([tool.name for tool in info.function_tools])
        last = messages[-1]
        if isinstance(last, ModelRequest) and any(
            part.part_kind == "tool-return" for part in last.parts
        ):
            yield "done"
            return
        yield {
            0: DeltaToolCall(
                name="run_code",
                json_args=json.dumps({"code": SNIPPET}),
                tool_call_id="call_1",
            )
        }

    return Agent(
        FunctionModel(stream_function=respond),
        tools=[glob_search, web_search, write_file],
        capabilities=[build_code_mode(), CodeModeEventsCapability()],
    )


async def _run(agent: Agent, queue: asyncio.Queue | None):
    async def consume(ctx, events):
        async for _ in events:
            pass

    return await agent.run(
        "go",
        deps=SimpleNamespace(ui_event_queue=queue),
        event_stream_handler=consume,
    )


def _drain(queue: asyncio.Queue) -> list:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


async def test_only_listed_tools_move_into_run_code():
    assert {"glob_search", "web_search"} <= CODE_MODE_TOOLS
    assert "write_file" not in CODE_MODE_TOOLS and "run_command" not in CODE_MODE_TOOLS
    offered: list[list[str]] = []

    await _run(_agent(offered), asyncio.Queue())

    assert sorted(offered[0]) == ["run_code", "write_file"]


async def test_each_snippet_call_is_reported_as_a_tool_call():
    queue: asyncio.Queue = asyncio.Queue()

    result = await _run(_agent([]), queue)

    events = _drain(queue)
    by_call: dict[str, list[str]] = {}
    for event in events:
        call_id = getattr(event, "tool_call_id", None) or event.value["toolCallId"]
        by_call.setdefault(call_id, []).append(str(event.type))
    assert set(by_call) == {"call_1__1", "call_1__2"}
    for kinds in by_call.values():
        assert kinds == [
            "EventType.CUSTOM",
            "EventType.TOOL_CALL_START",
            "EventType.TOOL_CALL_ARGS",
            "EventType.TOOL_CALL_END",
            "EventType.TOOL_CALL_RESULT",
        ]
    link = next(e for e in events if str(e.type) == "EventType.CUSTOM")
    assert link.name == "code_mode_call"
    assert link.value["parentToolCallId"] == "call_1"
    assert result.output == "done"


async def test_runs_without_a_chat_still_work():
    result = await _run(_agent([]), None)

    assert result.output == "done"


async def test_a_reloaded_chat_shows_the_snippet_calls():
    result = await _run(_agent([]), asyncio.Queue())
    stored = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json(result.all_messages())
    )

    display = _rebuild_display_messages(stored)

    parts = [p for row in display for p in row.get("parts", []) if p["type"] == "tool"]
    assert [p["toolName"] for p in parts] == ["run_code", "glob_search", "web_search"]
    nested = parts[1]
    assert nested["parentToolCallId"] == "call_1"
    assert json.loads(nested["args"]) == {"pattern": "*.py"}
    assert "a.py" in nested["output"]


def test_draft_links_a_snippet_call_to_its_run_code():
    from ag_ui.core import CustomEvent, ToolCallStartEvent

    draft = _DraftDisplayAccumulator(None, "run")
    draft.apply(
        CustomEvent(
            name="code_mode_call",
            value={"toolCallId": "call_1__1", "parentToolCallId": "call_1"},
        )
    )
    draft.apply(ToolCallStartEvent(tool_call_id="call_1__1", tool_call_name="grep"))

    (part,) = draft.parts
    assert part["toolName"] == "grep"
    assert part["parentToolCallId"] == "call_1"


def test_run_code_gets_a_longer_stream_wait():
    event = SimpleNamespace(part=SimpleNamespace(tool_name="run_code", args={}))

    assert _tool_timeout_from_event(event) == RUN_CODE_STREAM_TIMEOUT_SECONDS


def test_parent_call_id_only_reads_nested_ids():
    assert parent_call_id("toolu_01__3") == "toolu_01"
    assert parent_call_id("call__abc") is None
    assert parent_call_id("call_1") is None
