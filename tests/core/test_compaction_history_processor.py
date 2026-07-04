"""Tests for the mid-run compaction history processor.

The processor runs before every model request within a run (pydantic-ai
history_processors) and compacts context in-flight once it crosses the trigger.
"""

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

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
    yield


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
