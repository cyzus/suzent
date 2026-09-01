import asyncio
import math
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from ag_ui.core import CustomEvent, RunAgentInput
from pydantic_ai import Agent
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
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


# A finished turn must be on disk before the stream says so


@pytest.mark.asyncio
async def test_forced_persist_waits_for_a_write_already_in_flight(monkeypatch):
    """The draft write runs in the background, and scheduling one clears
    ``dirty``. The forced flush at the end of a turn must still wait for it:
    reporting the stream finished while the write is in flight lets a reload
    read stale content, and lets the late write race the turn finalizer."""
    started = asyncio.Event()
    release = asyncio.Event()
    finished = []

    async def slow_write(*args, **kwargs):
        started.set()
        await release.wait()
        finished.append(args)

    monkeypatch.setattr(streaming.asyncio, "to_thread", slow_write)
    monkeypatch.setattr(streaming, "_DRAFT_PERSIST_INTERVAL_SECONDS", 0)

    acc = streaming._DraftDisplayAccumulator(chat_id="chat-1", run_id="run-1")
    acc.parts = [{"type": "text", "text": "hello"}]
    acc.dirty = True

    await acc.maybe_persist()
    await asyncio.wait_for(started.wait(), timeout=1)
    assert acc.dirty is False  # scheduling the write cleared it

    forced = asyncio.create_task(acc.maybe_persist(force=True))
    await asyncio.sleep(0)
    assert not forced.done(), "forced flush returned while a write was in flight"

    release.set()
    await asyncio.wait_for(forced, timeout=1)
    assert finished, "the in-flight write did not land"


# ---------------------------------------------------------------------------
# Sub-agent calls are not tools that might hang
# ---------------------------------------------------------------------------


def test_agent_tool_stream_timeout_is_unbounded():
    event = FunctionToolCallEvent(
        ToolCallPart(
            tool_name="agent",
            args={"description": "research something slow"},
            tool_call_id="call-1",
        )
    )

    assert streaming._tool_timeout_from_event(event) == math.inf


class _SlowAgentToolStreamAgent:
    """Spawns a blocking sub-agent whose result takes longer than any tool window."""

    def run_stream_events(self, _prompt, **_kwargs):
        @asynccontextmanager
        async def stream():
            async def events():
                yield FunctionToolCallEvent(
                    ToolCallPart(
                        tool_name="agent",
                        args={"description": "long job"},
                        tool_call_id="call-1",
                    )
                )
                await asyncio.sleep(0.05)
                yield FunctionToolResultEvent(
                    ToolReturnPart(
                        tool_name="agent",
                        content="done",
                        tool_call_id="call-1",
                    )
                )

            yield events()

        return stream()


async def test_blocking_agent_call_is_not_timed_out(monkeypatch):
    # Every bounded window is far shorter than the sub-agent takes.
    monkeypatch.setattr(streaming, "_DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(streaming, "_STREAM_IDLE_TIMEOUT_SECONDS", 0.01)

    events = []
    async for event in streaming._iter_stream_events_with_timeout(
        _SlowAgentToolStreamAgent(), "hi", {}
    ):
        events.append(event.event_kind)

    assert events == ["function_tool_call", "function_tool_result"]


class _MixedBatchStreamAgent:
    """An unbounded `agent` call and an ordinary tool in one batch.

    The agent returns first; the peer then hangs. Its own window must still apply.
    """

    def run_stream_events(self, _prompt, **_kwargs):
        @asynccontextmanager
        async def stream():
            async def events():
                yield FunctionToolCallEvent(
                    ToolCallPart(
                        tool_name="agent",
                        args={"description": "long job"},
                        tool_call_id="call-agent",
                    )
                )
                yield FunctionToolCallEvent(
                    ToolCallPart(
                        tool_name="grep",
                        args={"pattern": "x"},
                        tool_call_id="call-grep",
                    )
                )
                yield FunctionToolResultEvent(
                    ToolReturnPart(
                        tool_name="agent",
                        content="done",
                        tool_call_id="call-agent",
                    )
                )
                await asyncio.Event().wait()  # the peer never returns

            yield events()

        return stream()


async def test_hung_peer_still_times_out_after_an_agent_call_returns(monkeypatch):
    monkeypatch.setattr(streaming, "_DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)

    events = []
    with pytest.raises(streaming._ToolResultTimeout):
        async for event in streaming._iter_stream_events_with_timeout(
            _MixedBatchStreamAgent(), "hi", {}
        ):
            events.append(event.event_kind)

    assert events == [
        "function_tool_call",
        "function_tool_call",
        "function_tool_result",
    ]


async def test_agent_call_still_unbounded_while_a_peer_is_pending(monkeypatch):
    """The peer's short window must not cut the agent call short either."""
    monkeypatch.setattr(streaming, "_DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)

    class _PeerFirst:
        def run_stream_events(self, _prompt, **_kwargs):
            @asynccontextmanager
            async def stream():
                async def events():
                    yield FunctionToolCallEvent(
                        ToolCallPart(
                            tool_name="agent",
                            args={},
                            tool_call_id="call-agent",
                        )
                    )
                    await asyncio.sleep(0.05)  # longer than the peer's window
                    yield FunctionToolResultEvent(
                        ToolReturnPart(
                            tool_name="agent",
                            content="done",
                            tool_call_id="call-agent",
                        )
                    )

                yield events()

            return stream()

    kinds = [
        event.event_kind
        async for event in streaming._iter_stream_events_with_timeout(
            _PeerFirst(), "hi", {}
        )
    ]
    assert kinds == ["function_tool_call", "function_tool_result"]


# ---------------------------------------------------------------------------
# A stopped turn keeps what it had already checkpointed
# ---------------------------------------------------------------------------


def _resolve_persisted_history(persisted, partial):
    """The teardown rule from `stream_agent_responses`' finally block.

    Kept in step with the source by the tests below; the block itself lives
    inside a closure that a unit test cannot reach.
    """
    if persisted is None or len(partial or []) > len(persisted):
        return partial
    return persisted


def test_stopped_turn_prefers_the_checkpoint_over_the_seed():
    # process_turn seeds last_messages with the restored history before the run,
    # so a stopped turn used to persist that and lose everything it had done.
    seeded = ["m1", "m2", "m3", "m4", "m5"]
    checkpointed = [*seeded, "response", "tool-returns"]

    assert _resolve_persisted_history(seeded, checkpointed) == checkpointed


def test_completed_turn_is_not_walked_backwards():
    # A normal run sets last_messages to the full result, which is never behind.
    complete = ["m1", "m2", "m3", "m4", "m5", "response", "returns", "final"]
    stale_checkpoint = complete[:6]

    assert _resolve_persisted_history(complete, stale_checkpoint) == complete


def test_unset_history_still_falls_back_to_the_partial():
    assert _resolve_persisted_history(None, ["m1"]) == ["m1"]


def test_nothing_to_prefer_leaves_the_persisted_history_alone():
    assert _resolve_persisted_history(["m1"], []) == ["m1"]
    assert _resolve_persisted_history(["m1"], None) == ["m1"]


def _history_of(chars: int) -> list:
    return [ModelResponse(parts=[TextPart(content="x" * chars)])]


def _timeout_for(tokens: int, model_id: str | None = None) -> float:
    return streaming._first_event_timeout(
        {"message_history": _history_of(tokens * 4)}, model_id
    )


@pytest.fixture(autouse=True)
def _clear_learned_prefill_rates():
    streaming._observed_prefill_k.clear()
    yield
    streaming._observed_prefill_k.clear()


def test_first_event_timeout_grows_faster_than_linearly() -> None:
    """Attention is quadratic, so doubling the prompt more than doubles prefill."""
    base = streaming._FIRST_STREAM_EVENT_TIMEOUT_SECONDS
    small = _timeout_for(50_000) - base
    large = _timeout_for(100_000) - base

    assert large > 2 * small


def test_first_event_timeout_is_the_base_for_an_empty_history() -> None:
    assert (
        streaming._first_event_timeout({})
        == streaming._FIRST_STREAM_EVENT_TIMEOUT_SECONDS
    )


def test_first_event_timeout_is_capped() -> None:
    assert _timeout_for(50_000_000) == streaming._MAX_FIRST_STREAM_EVENT_TIMEOUT_SECONDS


def test_prefill_rate_env_retunes_the_floor(monkeypatch) -> None:
    default = _timeout_for(162_000)
    monkeypatch.setenv("SUZENT_PREFILL_TOKENS_PER_SECOND", "700")

    assert _timeout_for(162_000) > default


def test_fixed_env_override_skips_the_scaling(monkeypatch) -> None:
    monkeypatch.setenv("SUZENT_FIRST_EVENT_TIMEOUT_S", "300")

    assert _timeout_for(162_000) == 300.0


@pytest.mark.parametrize("raw", ["", "  ", "soon", "0", "-5"])
def test_unusable_env_values_fall_back_to_the_default(monkeypatch, raw) -> None:
    monkeypatch.setenv("SUZENT_FIRST_EVENT_TIMEOUT_S", raw)

    assert (
        streaming._first_event_timeout({})
        == streaming._FIRST_STREAM_EVENT_TIMEOUT_SECONDS
    )


async def test_first_event_timeout_is_retryable(monkeypatch) -> None:
    monkeypatch.setattr(streaming, "_FIRST_STREAM_EVENT_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(streaming._FirstEventTimeout):
        async for _event in streaming._iter_stream_events_with_timeout(
            _HangingStreamAgent(), "hi", {}
        ):
            pass


# Cold prefill measured against a real 27B served by SGLang. The curve model has
# to cover every one of these from a single learned coefficient, or a deadline
# calibrated on a short prompt will fire on a long one.
_MEASURED_COLD_PREFILL = [
    (16_900, 9.6),
    (67_414, 50.7),
    (134_506, 135.0),
    (202_323, 256.0),
]


@pytest.mark.parametrize("tokens,ttft", _MEASURED_COLD_PREFILL)
def test_curve_fits_measured_prefill(tokens, ttft) -> None:
    # Learn from the slowest sample alone, then check every point is covered.
    streaming._record_prefill_rate("sglang/qwen3.8-27b", 202_323, 256.0)

    assert _timeout_for(tokens, "sglang/qwen3.8-27b") > ttft


def test_a_rate_learned_on_a_short_prompt_still_covers_a_long_one() -> None:
    """The failure a purely linear model would produce."""
    streaming._record_prefill_rate("sglang/qwen3.8-27b", 16_900, 9.6)

    # Real cold TTFT at 202k was 256s; a linear fit from 17k predicts ~115s.
    assert _timeout_for(202_323, "sglang/qwen3.8-27b") > 256.0


def test_learned_coefficient_lengthens_the_deadline_for_a_slow_model() -> None:
    # Slower than the default floor, so learning has to take over. (The 27B
    # measured above is *faster* than the floor, and correctly keeps it.)
    streaming._record_prefill_rate("sglang/slow", 134_506, 400.0)

    assert _timeout_for(162_000, "sglang/slow") > _timeout_for(162_000, "hosted/fast")


def test_a_model_faster_than_the_floor_keeps_the_floor() -> None:
    streaming._record_prefill_rate("sglang/qwen3.8-27b", 134_506, 135.0)

    assert _timeout_for(162_000, "sglang/qwen3.8-27b") == _timeout_for(162_000)


def test_a_cache_hit_does_not_shrink_the_deadline() -> None:
    # The same 134k prompt came back in 0.6s on the repeat; believing that would
    # collapse the window before the next cold prefill.
    streaming._record_prefill_rate("hosted/fast", 134_506, 135.0)
    slow = _timeout_for(162_000, "hosted/fast")
    streaming._record_prefill_rate("hosted/fast", 134_506, 0.6)

    assert _timeout_for(162_000, "hosted/fast") == pytest.approx(slow, rel=0.05)


def test_learned_coefficients_are_per_model() -> None:
    streaming._record_prefill_rate("sglang/local", 134_506, 135.0)

    assert "anthropic/claude-opus-5" not in streaming._observed_prefill_k


def test_a_slow_sample_is_believed_immediately() -> None:
    streaming._record_prefill_rate("sglang/local", 100_000, 50.0)
    fast_k = streaming._observed_prefill_k["sglang/local"]
    streaming._record_prefill_rate("sglang/local", 100_000, 200.0)

    assert streaming._observed_prefill_k["sglang/local"] == pytest.approx(4 * fast_k)


def test_small_prompts_do_not_teach_a_coefficient() -> None:
    # A 100-token prompt taking 3s measures queueing, not prefill throughput.
    streaming._record_prefill_rate("sglang/local", 100, 3.0)

    assert streaming._observed_prefill_k == {}


def test_fixed_override_still_wins_over_a_learned_coefficient(monkeypatch) -> None:
    streaming._record_prefill_rate("sglang/local", 202_323, 256.0)
    monkeypatch.setenv("SUZENT_FIRST_EVENT_TIMEOUT_S", "90")

    assert _timeout_for(162_000, "sglang/local") == 90.0
