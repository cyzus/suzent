import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from ag_ui.core import CustomEvent, RunAgentInput
from pydantic_ai import Agent
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import DeferredToolResults

from suzent import streaming
from suzent.tools.shell.shell_tools import RunCommandTool


def test_history_compatibility_retry_clears_deferred_tool_results() -> None:
    history = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="run_command",
                    args={"content": "pwd"},
                    tool_call_id="call-1",
                )
            ]
        )
    ]
    deferred = DeferredToolResults(approvals={"call-1": True})

    repaired, repaired_deferred, removed = streaming._strip_incompatible_tool_state(
        history, deferred
    )

    assert repaired == []
    assert repaired_deferred is None
    assert removed == 1


async def test_agui_event_stream_preserves_permission_custom_events() -> None:
    permission_event = CustomEvent(
        name="tool_permission_decision",
        value={
            "toolCallId": "call-1",
            "behavior": "allow",
            "reason": "Allowed by policy",
        },
    )

    async def source():
        yield permission_event

    event_stream = streaming._SuzentAGUIEventStream(
        RunAgentInput(
            thread_id="chat-1",
            run_id="run-1",
            messages=[],
            state=None,
            tools=[],
            context=[],
            forwarded_props=None,
        )
    )
    converted = [event async for event in event_stream.transform_stream(source())]

    assert permission_event in converted


class _HangingStreamAgent:
    def run_stream_events(self, _prompt, **_kwargs):
        @asynccontextmanager
        async def stream():
            async def events():
                await asyncio.Event().wait()
                yield None

            yield events()

        return stream()


class _SlowToolStreamAgent:
    def run_stream_events(self, _prompt, **_kwargs):
        @asynccontextmanager
        async def stream():
            async def events():
                yield FunctionToolCallEvent(
                    ToolCallPart(
                        tool_name="run_command",
                        args={"content": "sleep 1", "timeout": 1},
                        tool_call_id="call-1",
                    )
                )
                await asyncio.sleep(0.03)
                yield FunctionToolResultEvent(
                    ToolReturnPart(
                        tool_name="run_command",
                        content="done",
                        tool_call_id="call-1",
                    )
                )

            yield events()

        return stream()


async def test_stream_events_support_pydantic_v2_context_manager() -> None:
    agent = Agent(TestModel())

    events = [
        event
        async for event in streaming._iter_stream_events_with_timeout(
            agent, "hello", {}
        )
    ]

    assert events
    assert events[-1].event_kind == "agent_run_result"
    usage = streaming._run_result_usage(events[-1].result)
    assert usage.requests == 1


def test_function_tool_result_uses_v2_part_attribute() -> None:
    part = ToolReturnPart(
        tool_name="run_command",
        content="done",
        tool_call_id="call-1",
    )
    event = FunctionToolResultEvent(part)

    assert streaming._function_tool_result_part(event) is part


async def test_stream_events_timeout_when_first_event_never_arrives(monkeypatch):
    monkeypatch.setattr(streaming, "_FIRST_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(TimeoutError, match="Timed out waiting for LLM stream"):
        async for _event in streaming._iter_stream_events_with_timeout(
            _HangingStreamAgent(), "hi", {}
        ):
            pass


class _HangingToolStreamAgent:
    """Emits a tool call but never produces its result."""

    def run_stream_events(self, _prompt, **_kwargs):
        @asynccontextmanager
        async def stream():
            async def events():
                yield FunctionToolCallEvent(
                    ToolCallPart(
                        tool_name="run_command",
                        args={"content": "sleep 999", "timeout": 1},
                        tool_call_id="call-1",
                    )
                )
                await asyncio.Event().wait()

            yield events()

        return stream()


async def test_tool_result_timeout_raises_recoverable_error(monkeypatch):
    # Force the tool-result wait to fire quickly.
    monkeypatch.setattr(streaming, "_DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        RunCommandTool, "stream_wait_timeout_seconds", classmethod(lambda cls, t: 0.01)
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
            tool_name="run_command",
            args={"content": "sleep 999"},
            tool_call_id="call-1",
        )
    )

    timeout = streaming._tool_timeout_from_event(event)

    assert timeout == RunCommandTool.stream_wait_timeout_seconds(None)


def test_bash_tool_stream_timeout_uses_explicit_timeout_when_provided():
    event = FunctionToolCallEvent(
        ToolCallPart(
            tool_name="run_command",
            args={"content": "sleep 999", "timeout": 5},
            tool_call_id="call-1",
        )
    )

    timeout = streaming._tool_timeout_from_event(event)

    assert timeout == RunCommandTool.stream_wait_timeout_seconds(5)


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


def test_permission_decision_payload_and_resolution_are_persisted():
    from suzent.permissions.models import (
        CommandDecision,
        PermissionDecision,
        PermissionDecisionSource,
        PermissionRisk,
    )

    decision = PermissionDecision(
        behavior=CommandDecision.ALLOW,
        reason="Classifier found no risky side effect",
        reasonCode="auto_classifier_allow",
        risk=PermissionRisk.LOW,
        source=PermissionDecisionSource.AUTO_CLASSIFIER,
        metadata={
            "confidence": "high",
            "risk_categories": ["network"],
            "reviewer_model": "review-model",
        },
    )
    payload = streaming._permission_decision_payload(
        tool_call_id="call-1",
        tool_name="social_message",
        decision=decision,
    )
    acc = streaming._DraftDisplayAccumulator(chat_id="chat-1", run_id="run-1")
    acc.apply(
        SimpleNamespace(
            type="CUSTOM",
            name="tool_permission_decision",
            value=payload,
        )
    )
    resolution = {
        "toolCallId": "call-1",
        "behavior": "allow",
        "source": "user",
        "actionId": "allow_once",
        "scope": "once",
    }
    acc.apply(
        SimpleNamespace(
            type="CUSTOM",
            name="tool_permission_resolution",
            value=resolution,
        )
    )

    assert payload["source"] == "auto_classifier"
    assert payload["confidence"] == "high"
    assert acc.parts[0]["permissionDecision"] == payload
    assert acc.parts[0]["permissionResolution"] == resolution
