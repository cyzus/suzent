"""Tests for the mid-run compaction history processor.

The processor runs before every model request within a run (pydantic-ai
history_processors) and compacts context in-flight once it crosses the trigger.
"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RequestUsage,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

import suzent.core.context_compressor as cc
from suzent.config import CONFIG
from suzent.core.context_compressor import (
    COMPACTION_SUMMARY_REQUEST_MARKER,
    COMPACTION_SUMMARY_RESPONSE_MARKER,
    make_compaction_history_processor,
    _message_has_compaction_marker,
)


@pytest.fixture(autouse=True)
def _quiet_bus_and_config(monkeypatch):
    # Don't broadcast to the real event bus during tests.
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", lambda p: None)
    # Deterministic thresholds.
    monkeypatch.setattr(CONFIG, "compaction_keep_recent_turns", 3, raising=False)
    # Suppression state is module-level and keyed by chat_id; every test uses
    # "c1", so it must not leak between them.
    cc.reset_compaction_suppression()
    yield
    cc.reset_compaction_suppression()


def _history(n=12):
    # Realistic in-run history: alternating turns, ending with a ModelRequest (the
    # pending prompt/tool-return that the model is about to answer). pydantic-ai
    # requires processed history to end with a ModelRequest.
    msgs = [
        ModelRequest(parts=[UserPromptPart(content=f"m{i}")])
        if i % 2 == 0
        else ModelResponse(parts=[TextPart(content=f"a{i}")])
        for i in range(n - 1)
    ]
    msgs.append(ModelRequest(parts=[UserPromptPart(content="pending")]))
    return msgs


def _fake_compaction(monkeypatch):
    """Stub _perform_compression with a deterministic summary-framed result."""

    async def fake(self, messages, focus=None, background_flush=False):
        sr = ModelRequest(
            parts=[UserPromptPart(content=f"{COMPACTION_SUMMARY_REQUEST_MARKER}\np")]
        )
        sp = ModelResponse(
            parts=[TextPart(content=f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\nsum")]
        )
        keep = CONFIG.compaction_keep_recent_turns * 2
        return messages[:1] + [sr, sp] + messages[-keep:]

    monkeypatch.setattr(
        cc.ContextCompressor, "_perform_compression", fake, raising=True
    )


def _ctx(stateless=False, input_tokens=0):
    # ``input_tokens`` models pydantic-ai's cumulative RunUsage. The processor must
    # NOT key its trigger off this counter (it only ever grows within a run); it is
    # kept on the fake ctx to prove changing it does not change the decision.
    return SimpleNamespace(
        deps=SimpleNamespace(stateless=stateless, chat_id="c1", user_id="u1"),
        usage=SimpleNamespace(input_tokens=input_tokens),
    )


@pytest.mark.asyncio
async def test_compacts_when_over_trigger(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.01, raising=False)
    _fake_compaction(monkeypatch)

    proc = make_compaction_history_processor()
    hist = _history(12)
    hist[1] = ModelResponse(parts=[TextPart(content="old work " * 1000)])
    out = await proc(_ctx(), hist)

    assert len(out) < len(hist)
    assert any(_message_has_compaction_marker(m) for m in out)
    # pydantic-ai invariant: processed history ends with a ModelRequest.
    assert isinstance(out[-1], ModelRequest)


@pytest.mark.asyncio
async def test_noop_under_trigger(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 10_000_000, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.80, raising=False)
    _fake_compaction(monkeypatch)

    proc = make_compaction_history_processor()
    hist = _history(12)
    out = await proc(_ctx(), hist)

    assert out is hist  # untouched


@pytest.mark.asyncio
async def test_skips_stateless(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.01, raising=False)
    _fake_compaction(monkeypatch)

    proc = make_compaction_history_processor()
    hist = _history(12)
    out = await proc(_ctx(stateless=True), hist)

    assert out is hist


@pytest.mark.asyncio
async def test_trigger_ignores_cumulative_run_usage(monkeypatch):
    # The trigger must key off the CURRENT history size, not ctx.usage. A tiny
    # history that sits under budget must no-op even when the cumulative run usage
    # (which pydantic-ai never resets within a run) is huge.
    monkeypatch.setattr(CONFIG, "max_context_tokens", 10_000_000, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.80, raising=False)
    _fake_compaction(monkeypatch)

    proc = make_compaction_history_processor()
    hist = _history(12)
    out = await proc(_ctx(input_tokens=9_000_000), hist)

    assert out is hist  # cumulative usage does not force a compaction


@pytest.mark.asyncio
async def test_does_not_reloop_after_history_shrinks(monkeypatch):
    # Regression: once a pass shrinks the history under budget, a second pass with
    # the SAME (only-growing) cumulative usage must observe the reduction via the
    # message-size estimate and no-op — otherwise the processor loops every request.
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.80, raising=False)
    _fake_compaction(monkeypatch)

    proc = make_compaction_history_processor()

    # First pass: large history is over trigger -> compacts down. Pad a message in
    # the compressible middle so the summary pair genuinely shrinks it under budget
    # (the first and last-N messages are preserved by compaction).
    big = _history(40)
    big[10] = ModelResponse(parts=[TextPart(content="x" * 4000)])
    ctx = _ctx(input_tokens=1000)  # cumulative usage well over any threshold
    compacted = await proc(ctx, big)
    assert len(compacted) < len(big)

    # Second pass: feed the compacted (small) history back with usage still high.
    # It is now under budget, so the processor must leave it untouched.
    out = await proc(ctx, compacted)
    assert out is compacted


@pytest.mark.asyncio
async def test_skips_when_compacted_tail_is_invalid(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.01, raising=False)

    # Compaction yields a tail ending in a ModelResponse -> violates invariant.
    async def bad(self, messages, focus=None, background_flush=False):
        return messages[:1] + [ModelResponse(parts=[TextPart(content="x")])]

    monkeypatch.setattr(cc.ContextCompressor, "_perform_compression", bad)

    proc = make_compaction_history_processor()
    hist = _history(12)
    out = await proc(_ctx(), hist)

    # Falls back to the original (which ends with a ModelResponse only if n even;
    # here it returns the untouched input, preserving whatever pydantic-ai gave us).
    assert out is hist


@pytest.mark.asyncio
async def test_compaction_keeps_tool_call_with_tail_result(monkeypatch):
    monkeypatch.setattr(CONFIG, "compaction_keep_recent_turns", 1, raising=False)

    async def fake_summary(self, messages, focus=None):
        return "Archived history"

    monkeypatch.setattr(
        cc.ContextCompressor,
        "_summarize_with_retry",
        fake_summary,
    )
    compressor = cc.ContextCompressor(llm_client=object())
    history = [
        ModelRequest(parts=[UserPromptPart(content="old")]),
        ModelResponse(parts=[TextPart(content="old answer")]),
        ModelRequest(parts=[UserPromptPart(content="run")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="bash_execute",
                    tool_call_id="call-1",
                    args={"command": "pwd"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="bash_execute",
                    tool_call_id="call-1",
                    content="ok",
                )
            ]
        ),
    ]

    out = await compressor._perform_compression(history)

    call_index = next(
        index
        for index, message in enumerate(out)
        if isinstance(message, ModelResponse)
        and any(isinstance(part, ToolCallPart) for part in message.parts)
    )
    result_index = next(
        index
        for index, message in enumerate(out)
        if isinstance(message, ModelRequest)
        and any(isinstance(part, ToolReturnPart) for part in message.parts)
    )
    assert call_index < result_index


@pytest.mark.asyncio
async def test_compaction_anchors_current_request_outside_recent_tail(monkeypatch):
    monkeypatch.setattr(CONFIG, "compaction_keep_recent_turns", 1, raising=False)

    async def fake_summary(self, messages, focus=None):
        return "## 1. Primary Request and Intent\nOld topic"

    monkeypatch.setattr(cc.ContextCompressor, "_summarize_with_retry", fake_summary)
    history = [
        ModelRequest(parts=[UserPromptPart(content="old question")]),
        ModelResponse(parts=[TextPart(content="old answer " * 1000)]),
        ModelRequest(parts=[UserPromptPart(content="start the voice work")]),
    ]
    history.extend(
        ModelResponse(parts=[TextPart(content=f"progress {index}")])
        if index % 2 == 0
        else ModelRequest(parts=[ToolReturnPart(tool_name="run", content="ok")])
        for index in range(8)
    )

    out = await cc.ContextCompressor(llm_client=object())._perform_compression(history)

    summary = out[2].parts[0].content
    assert "## Active user request (verbatim)\nstart the voice work" in summary
    assert cc._latest_user_prompt(out) == "start the voice work"


@pytest.mark.asyncio
async def test_incomplete_summary_is_rejected_after_larger_output_budget():
    calls = []

    class StubLLM:
        async def complete(self, **kwargs):
            calls.append(kwargs)
            return "<summary>## 1. Primary Request and Intent\ncut off</summary>"

    compressor = cc.ContextCompressor(llm_client=StubLLM())
    summary = await compressor._summarize_with_retry(_history(4))

    assert summary == ""
    assert len(calls) == 3
    assert all(call["max_tokens"] == cc.SUMMARY_MAX_TOKENS for call in calls)


@pytest.mark.asyncio
async def test_processor_leaves_usage_reporting_to_the_capability(monkeypatch):
    """A second report per request made the panel alternate between two numbers."""
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100_000, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.99, raising=False)

    seen = []
    monkeypatch.setattr(
        "suzent.core.stream_registry.emit_bus_event", lambda p: seen.append(p)
    )

    proc = make_compaction_history_processor()
    hist = _history(12)
    out = await proc(_ctx(), hist)

    assert out is hist
    assert [e for e in seen if e["event"] == "context_usage"] == []


def test_trigger_counts_recorded_schema_overhead_before_any_measurement():
    hist = [ModelRequest(parts=[UserPromptPart(content="x" * 4000)])]
    ctx = _ctx()
    ctx.deps.context_overhead_estimate = 30_000

    assert cc.context_input_tokens(ctx, hist) == 31_000


def test_trigger_prefers_the_provider_measurement_over_the_recorded_overhead():
    hist = [
        ModelRequest(parts=[UserPromptPart(content="x" * 400)]),
        ModelResponse(
            parts=[TextPart(content="y" * 400)],
            usage=RequestUsage(input_tokens=9000),
        ),
    ]
    ctx = _ctx()
    ctx.deps.context_overhead_estimate = 30_000

    assert cc.context_input_tokens(ctx, hist) == 9100


@pytest.mark.asyncio
async def test_stateless_runs_report_no_context_usage(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100_000, raising=False)

    seen = []
    monkeypatch.setattr(
        "suzent.core.stream_registry.emit_bus_event", lambda p: seen.append(p)
    )

    proc = make_compaction_history_processor()
    await proc(_ctx(stateless=True), _history(12))

    assert seen == []


@pytest.mark.asyncio
async def test_every_started_pass_reports_a_terminal_stage(monkeypatch):
    """A surface that animates 'start' must always be told when the pass ends."""
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.01, raising=False)

    # Already summary-framed and unable to shrink further: the pass starts and
    # then finds nothing to drop.
    async def no_reduction(self, messages, focus=None, background_flush=False):
        return messages

    monkeypatch.setattr(
        cc.ContextCompressor, "_perform_compression", no_reduction, raising=True
    )

    seen = []
    monkeypatch.setattr(
        "suzent.core.stream_registry.emit_bus_event", lambda p: seen.append(p)
    )

    hist = _history(12)
    hist[3] = ModelResponse(
        parts=[TextPart(content=f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\nsum")]
    )
    assert _message_has_compaction_marker(hist[3])

    await make_compaction_history_processor()(_ctx(), hist)

    stages = [e["stage"] for e in seen if e["event"] == "auto_compaction"]
    assert stages[0] == "start"
    assert stages[-1] in {"complete", "skipped", "error"}


@pytest.mark.asyncio
async def test_estimate_drops_after_compaction_despite_stale_usage(monkeypatch):
    """A retained tail message's pre-compaction usage must not inflate the estimate.

    Regression: ``context_overhead_tokens`` read the provider count for a prompt
    that still contained the compacted-away history, subtracted the new (tiny)
    history from it, and reported the difference as fixed overhead — so the
    estimate after a compaction equalled the estimate before it and auto-compact
    re-fired on every subsequent request.
    """
    from pydantic_ai.messages import RequestUsage

    limit = 200_000
    big = "x" * 4000  # ~1k tokens each

    msgs = [
        ModelRequest(parts=[UserPromptPart(content=big)])
        if i % 2 == 0
        else ModelResponse(parts=[TextPart(content=big)])
        for i in range(39)
    ]
    # The provider counted the whole pre-compaction prompt on the last response.
    msgs.append(
        ModelResponse(
            parts=[TextPart(content=big)], usage=RequestUsage(input_tokens=170_000)
        )
    )
    msgs.append(ModelRequest(parts=[UserPromptPart(content="pending")]))

    before = cc.estimate_tokens(msgs, limit).estimated_tokens

    keep = CONFIG.compaction_keep_recent_turns * 2
    compacted = (
        msgs[:1]
        + [
            ModelRequest(
                parts=[
                    UserPromptPart(content=f"{COMPACTION_SUMMARY_REQUEST_MARKER}\np")
                ]
            ),
            ModelResponse(
                parts=[TextPart(content=f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\nsum")]
            ),
        ]
        + cc._clear_stale_usage(msgs[-keep:])
    )
    after = cc.estimate_tokens(compacted, limit).estimated_tokens

    assert after < before
    assert after < limit * CONFIG.context_compaction_trigger


@pytest.mark.asyncio
async def test_ineffective_compaction_is_not_retried(monkeypatch):
    """A completed pass that stays over the trigger must not re-fire every request."""
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.01, raising=False)
    _fake_compaction(monkeypatch)

    calls = []
    original = cc.ContextCompressor._perform_compression

    async def counting(self, messages, focus=None, background_flush=False):
        calls.append(len(messages))
        return await original(
            self, messages, focus=focus, background_flush=background_flush
        )

    monkeypatch.setattr(cc.ContextCompressor, "_perform_compression", counting)

    proc = make_compaction_history_processor()
    out = await proc(_ctx(), _history(12))
    assert len(calls) == 1

    # Same (already compacted, still over trigger) history: no second attempt.
    again = await proc(_ctx(), out)
    assert len(calls) == 1
    assert again is out


@pytest.mark.asyncio
async def test_suppression_rearms_when_history_grows(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.01, raising=False)
    _fake_compaction(monkeypatch)

    proc = make_compaction_history_processor()
    history = _history(12)
    history[1] = ModelResponse(parts=[TextPart(content="old work " * 1000)])
    out = await proc(_ctx(), history)
    assert await proc(_ctx(), out) is out  # suppressed

    grown = out[:1] + [ModelResponse(parts=[TextPart(content="y" * 20_000)])] + out[1:]
    regrown = await proc(_ctx(), grown)
    assert len(regrown) < len(grown)


def _long_tool_run(request: str, rounds: int = 20) -> list:
    """A chat whose current request has scrolled out of the recent tail."""
    hist = [
        ModelRequest(parts=[UserPromptPart(content="Diagnose the voice feature")]),
        ModelResponse(parts=[TextPart(content="Diagnosis: ...")]),
        ModelRequest(parts=[UserPromptPart(content=request)]),
    ]
    for i in range(rounds):
        hist.append(
            ModelResponse(parts=[ToolCallPart("read_file", {"p": "x" * 400}, f"t{i}")])
        )
        hist.append(ModelRequest(parts=[ToolReturnPart("read_file", "ok", f"t{i}")]))
    return hist


def _summary_text(messages: list) -> str:
    return "\n".join(
        part.content
        for m in messages
        if isinstance(m, ModelResponse)
        for part in m.parts
        if isinstance(part, TextPart)
        and COMPACTION_SUMMARY_RESPONSE_MARKER in part.content
    )


@pytest.mark.asyncio
async def test_timed_out_compaction_keeps_the_current_request(monkeypatch):
    """The hard-trim fallback left only the chat's first request, and the agent
    went back to it as if it were still the task."""
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100_000, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.0001, raising=False)
    monkeypatch.setattr(CONFIG, "compaction_timeout_seconds", 0.01, raising=False)

    async def slow(self, messages, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(cc.ContextCompressor, "_perform_compression", slow)
    hist = _long_tool_run("Go ahead and implement the plan")

    out = await make_compaction_history_processor()(_ctx(), hist)

    assert out is hist
    assert not _summary_text(out)


@pytest.mark.asyncio
async def test_turn_boundary_timeout_keeps_the_current_request(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 100, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.01, raising=False)
    monkeypatch.setattr(CONFIG, "compaction_timeout_seconds", 0.01, raising=False)

    async def slow(self, messages, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(cc.ContextCompressor, "_perform_compression", slow)
    compressor = cc.ContextCompressor(chat_id="c1", user_id="u1")

    history = _long_tool_run("Keep refactoring")
    out = await compressor.compress_messages(history)

    assert out is history


def test_summary_anchor_strips_runtime_reminders():
    from suzent.core.system_reminder import wrap_in_system_reminder

    reminder = wrap_in_system_reminder("internal guidance")
    hist = _long_tool_run(f"Fix the echo gate\n{reminder}")

    summary = _summary_text(cc.build_summary_pair("Earlier work.", hist))

    assert "Fix the echo gate" in summary
    assert "internal guidance" not in summary


@pytest.mark.asyncio
async def test_compaction_time_is_tracked_per_chat():
    before = cc.compaction_seconds("c-track")
    with cc._track_compaction("c-track"):
        await asyncio.sleep(0.05)
        assert cc.compaction_seconds("c-track") - before >= 0.04
    assert cc.compaction_seconds("c-track") - before >= 0.05
    assert cc.compaction_seconds("other") == 0.0
