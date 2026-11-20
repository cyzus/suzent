"""A run survives a model request that fails, and says so in the transcript."""

import json
from collections.abc import AsyncIterator

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

import suzent.streaming as streaming
from suzent.core.agent_deps import AgentDeps
from suzent.core.model_recovery import (
    FailureKind,
    classify_model_failure,
    retry_delay,
)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []

    async def record(control, seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(streaming, "_wait_unless_cancelled", record)
    return waits


def _events(chunks: list[str]) -> list[dict]:
    events = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def _run(agent: Agent, deps: AgentDeps) -> list[dict]:
    chunks = [
        chunk
        async for chunk in streaming.stream_agent_responses(agent, "hello", deps=deps)
    ]
    return _events(chunks)


def _recoveries(events: list[dict]) -> list[dict]:
    return [
        event["value"]
        for event in events
        if event.get("type") == "CUSTOM" and event.get("name") == "model_recovery"
    ]


async def test_a_reply_cut_off_midway_is_streamed_again() -> None:
    calls = 0

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield "Here is the first half"
            raise ModelConnectionError("qwen", "Connection error.")
        yield "Here is the whole reply."

    deps = AgentDeps()
    events = await _run(Agent(FunctionModel(stream_function=stream)), deps)

    assert calls == 2
    assert not [event for event in events if event.get("type") == "RUN_ERROR"]
    [recovery] = _recoveries(events)
    assert recovery["attempt"] == 1
    assert recovery["reason"] == "connection"

    parts = deps.streamed_message["parts"]
    texts = [part["text"] for part in parts if part["type"] == "text"]
    assert texts == ["Here is the whole reply."]
    assert [part["type"] for part in parts] == ["model-notice", "text"]


async def test_finished_tool_calls_are_not_run_again() -> None:
    calls = 0
    tool_runs = 0

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {0: DeltaToolCall(name="ping", json_args="{}", tool_call_id="c1")}
            return
        if calls == 2:
            yield "Pong came back, now writing"
            raise ModelConnectionError("qwen", "Connection error.")
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        assert any(isinstance(part, ToolReturnPart) for part in last.parts)
        yield "Done."

    agent = Agent(FunctionModel(stream_function=stream))

    @agent.tool_plain
    def ping() -> str:
        nonlocal tool_runs
        tool_runs += 1
        return "pong"

    deps = AgentDeps()
    events = await _run(agent, deps)

    assert tool_runs == 1
    assert calls == 3
    [usage] = [
        event["value"]
        for event in events
        if event.get("type") == "CUSTOM" and event.get("name") == "usage_update"
    ]
    assert usage["requests"] == 3
    assert len(_recoveries(events)) == 1
    parts = deps.streamed_message["parts"]
    assert [part["type"] for part in parts if part.get("text") != ""] == [
        "tool",
        "model-notice",
        "text",
    ]
    assert parts[-1]["text"] == "Done."


async def test_gives_up_after_three_retries(no_backoff: list[float]) -> None:
    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        raise ModelTimeoutError("deepseek", "Request timed out.")
        yield ""

    events = await _run(Agent(FunctionModel(stream_function=stream)), AgentDeps())

    assert no_backoff == [2.0, 5.0, 15.0]
    assert [r["attempt"] for r in _recoveries(events)] == [1, 2, 3]
    [error] = [event for event in events if event.get("type") == "RUN_ERROR"]
    assert error["code"] == "model_stalled"


async def test_a_rejected_key_is_not_retried() -> None:
    calls = 0

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        nonlocal calls
        calls += 1
        raise ModelHTTPError.for_category(
            ModelAuthenticationError, status_code=401, model_name="m"
        )
        yield ""

    events = await _run(Agent(FunctionModel(stream_function=stream)), AgentDeps())

    assert calls == 1
    assert not _recoveries(events)
    [error] = [event for event in events if event.get("type") == "RUN_ERROR"]
    assert error["code"] == "model_auth"


def test_rate_limits_wait_as_long_as_the_provider_asks() -> None:
    error = ModelHTTPError.for_category(
        ModelRateLimitError, status_code=429, model_name="m", retry_after=30
    )
    failure = classify_model_failure(error)
    assert failure is not None and failure.kind is FailureKind.RATE_LIMIT
    assert retry_delay(failure, 1) == 30


def test_a_wait_longer_than_a_minute_is_not_retried() -> None:
    error = ModelHTTPError.for_category(
        ModelRateLimitError, status_code=429, model_name="m", retry_after=3600
    )
    failure = classify_model_failure(error)
    assert failure is not None
    assert retry_delay(failure, 1) is None


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (429, FailureKind.RATE_LIMIT),
        (503, FailureKind.OVERLOADED),
        (402, FailureKind.QUOTA),
        (400, FailureKind.REJECTED),
    ],
)
def test_plain_http_errors_are_sorted_by_status(status: int, kind: FailureKind) -> None:
    failure = classify_model_failure(ModelHTTPError(status_code=status, model_name="m"))
    assert failure is not None and failure.kind is kind


def test_a_transport_error_from_below_the_sdk_counts_as_a_dropped_connection() -> None:
    class RemoteProtocolError(Exception):
        pass

    wrapped = RuntimeError("stream broke")
    wrapped.__cause__ = RemoteProtocolError("peer closed connection")
    failure = classify_model_failure(wrapped)
    assert failure is not None and failure.kind is FailureKind.CONNECTION


def test_the_detail_is_the_provider_message_not_the_raw_body() -> None:
    error = ModelHTTPError(
        status_code=402,
        model_name="deepseek-chat",
        body={"error": {"message": "Insufficient Balance", "type": "unknown_error"}},
    )
    failure = classify_model_failure(error)
    assert failure is not None
    assert failure.kind is FailureKind.QUOTA
    assert failure.detail == "HTTP 402: Insufficient Balance"


def test_errors_that_are_not_the_model_are_left_alone() -> None:
    assert classify_model_failure(ValueError("bad tool args")) is None
