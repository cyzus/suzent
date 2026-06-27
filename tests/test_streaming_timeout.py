import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from suzent import streaming
from suzent.tools.shell.bash_tool import BashTool


class _HangingStreamAgent:
    async def run_stream_events(self, _prompt, **_kwargs):
        await asyncio.Event().wait()
        yield None


class _SlowToolStreamAgent:
    async def run_stream_events(self, _prompt, **_kwargs):
        yield FunctionToolCallEvent(
            ToolCallPart(
                tool_name="bash_execute",
                args={"content": "sleep 1", "timeout": 1},
                tool_call_id="call-1",
            )
        )
        await asyncio.sleep(0.03)
        yield FunctionToolResultEvent(
            ToolReturnPart(
                tool_name="bash_execute",
                content="done",
                tool_call_id="call-1",
            )
        )


async def test_stream_events_timeout_when_first_event_never_arrives(monkeypatch):
    monkeypatch.setattr(streaming, "_FIRST_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(TimeoutError, match="Timed out waiting for LLM stream"):
        async for _event in streaming._iter_stream_events_with_timeout(
            _HangingStreamAgent(), "hi", {}
        ):
            pass


class _HangingToolStreamAgent:
    """Emits a tool call but never produces its result."""

    async def run_stream_events(self, _prompt, **_kwargs):
        yield FunctionToolCallEvent(
            ToolCallPart(
                tool_name="bash_execute",
                args={"content": "sleep 999", "timeout": 1},
                tool_call_id="call-1",
            )
        )
        await asyncio.Event().wait()


async def test_tool_result_timeout_raises_recoverable_error(monkeypatch):
    # Force the tool-result wait to fire quickly.
    monkeypatch.setattr(streaming, "_DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        BashTool, "stream_wait_timeout_seconds", classmethod(lambda cls, t: 0.01)
    )

    events = []
    with pytest.raises(streaming._ToolResultTimeout) as exc_info:
        async for event in streaming._iter_stream_events_with_timeout(
            _HangingToolStreamAgent(), "hi", {}
        ):
            events.append(event.event_kind)

    # The tool call is delivered; only the (never-arriving) result times out.
    assert events == ["function_tool_call"]
    assert exc_info.value.timeout == 0.01
    # Recoverable timeout is distinct from the fatal stream timeouts.
    assert isinstance(exc_info.value, TimeoutError)


async def test_first_event_timeout_is_not_recoverable(monkeypatch):
    monkeypatch.setattr(streaming, "_FIRST_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(TimeoutError) as exc_info:
        async for _event in streaming._iter_stream_events_with_timeout(
            _HangingStreamAgent(), "hi", {}
        ):
            pass

    assert not isinstance(exc_info.value, streaming._ToolResultTimeout)


async def test_stream_events_do_not_idle_timeout_while_tool_is_running(monkeypatch):
    monkeypatch.setattr(streaming, "_STREAM_IDLE_TIMEOUT_SECONDS", 0.01)

    events = []
    async for event in streaming._iter_stream_events_with_timeout(
        _SlowToolStreamAgent(), "hi", {}
    ):
        events.append(event.event_kind)

    assert events == ["function_tool_call", "function_tool_result"]


def test_bash_tool_stream_timeout_uses_default_when_unspecified():
    event = FunctionToolCallEvent(
        ToolCallPart(
            tool_name="bash_execute",
            args={"content": "sleep 999"},
            tool_call_id="call-1",
        )
    )

    timeout = streaming._tool_timeout_from_event(event)

    assert timeout == BashTool.stream_wait_timeout_seconds(None)


def test_bash_tool_stream_timeout_uses_explicit_timeout_when_provided():
    event = FunctionToolCallEvent(
        ToolCallPart(
            tool_name="bash_execute",
            args={"content": "sleep 999", "timeout": 5},
            tool_call_id="call-1",
        )
    )

    timeout = streaming._tool_timeout_from_event(event)

    assert timeout == BashTool.stream_wait_timeout_seconds(5)


def test_non_bash_tool_stream_timeout_defaults_to_one_minute():
    event = FunctionToolCallEvent(
        ToolCallPart(
            tool_name="other_tool",
            args={"query": "slow thing"},
            tool_call_id="call-1",
        )
    )

    assert streaming._tool_timeout_from_event(event) == 60.0


def test_draft_accumulator_persists_citation_sources():
    acc = streaming._DraftDisplayAccumulator(chat_id="chat-1", run_id="run-1")

    acc.apply(
        SimpleNamespace(
            type="CUSTOM",
            name="citation_sources",
            value={
                "sources": [
                    {
                        "id": "t0_src_1",
                        "type": "search",
                        "title": "Example",
                        "url": "https://example.com",
                    }
                ]
            },
        )
    )

    assert acc.parts == [
        {
            "type": "citation-sources",
            "citationSources": [
                {
                    "id": "t0_src_1",
                    "type": "search",
                    "title": "Example",
                    "url": "https://example.com",
                }
            ],
        }
    ]
    assert acc.dirty is True


def test_draft_accumulator_merges_citation_sources_by_id():
    acc = streaming._DraftDisplayAccumulator(chat_id="chat-1", run_id="run-1")

    acc.apply(
        SimpleNamespace(
            type="CUSTOM",
            name="citation_sources",
            value={"sources": [{"id": "t0_src_1", "type": "search", "title": "Old"}]},
        )
    )
    acc.apply(
        SimpleNamespace(
            type="CUSTOM",
            name="citation_sources",
            value={
                "sources": [
                    {"id": "t0_src_1", "type": "search", "title": "New"},
                    {"id": "t0_src_2", "type": "webpage", "title": "Page"},
                ]
            },
        )
    )

    assert acc.parts == [
        {
            "type": "citation-sources",
            "citationSources": [
                {"id": "t0_src_1", "type": "search", "title": "New"},
                {"id": "t0_src_2", "type": "webpage", "title": "Page"},
            ],
        }
    ]


def test_draft_accumulator_snapshots_final_citation_sources():
    acc = streaming._DraftDisplayAccumulator(chat_id="chat-1", run_id="run-1")

    acc.apply_citation_sources(
        [{"id": "t0_src_1", "type": "search", "title": "Example"}]
    )

    assert acc.parts == [
        {
            "type": "citation-sources",
            "citationSources": [
                {"id": "t0_src_1", "type": "search", "title": "Example"}
            ],
        }
    ]
