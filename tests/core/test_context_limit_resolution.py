"""Tests for the model-derived context budget.

The compaction trigger used to be one fixed token count for every model. It is
now the active model's own input window, with ``max_context_tokens`` acting only
as an optional ceiling.
"""

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

import suzent.core.context_compressor as cc
from suzent.config import CONFIG
from suzent.core.context_compressor import (
    DEFAULT_CONTEXT_LIMIT_TOKENS,
    make_compaction_history_processor,
    resolve_context_limit,
)
from suzent.core.model_registry import ModelCapabilities


def _fake_registry(monkeypatch, windows: dict[str, ModelCapabilities]):
    monkeypatch.setattr(
        "suzent.core.model_registry.get_model_registry",
        lambda: SimpleNamespace(get_capabilities=lambda mid: windows.get(mid)),
    )


def _caps(max_input=0, max_output=0):
    return ModelCapabilities(max_input_tokens=max_input, max_output_tokens=max_output)


@pytest.fixture(autouse=True)
def _auto_budget(monkeypatch):
    # 0 == adaptive, the shipped default.
    monkeypatch.setattr(CONFIG, "max_context_tokens", 0, raising=False)
    yield


def test_uses_the_models_input_window(monkeypatch):
    _fake_registry(
        monkeypatch, {"g/big": _caps(max_input=1_000_000, max_output=65_536)}
    )

    # The output reservation is not part of the prompt being sized.
    assert resolve_context_limit("g/big") == 1_000_000


def test_small_model_gets_a_small_budget(monkeypatch):
    _fake_registry(monkeypatch, {"o/small": _caps(max_input=128_000)})

    assert resolve_context_limit("o/small") == 128_000


def test_unknown_model_falls_back_to_the_default(monkeypatch):
    _fake_registry(monkeypatch, {})

    assert resolve_context_limit("who/knows") == DEFAULT_CONTEXT_LIMIT_TOKENS
    assert resolve_context_limit(None) == DEFAULT_CONTEXT_LIMIT_TOKENS


def test_configured_value_caps_a_larger_window(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 200_000, raising=False)
    _fake_registry(monkeypatch, {"g/big": _caps(max_input=1_000_000)})

    assert resolve_context_limit("g/big") == 200_000


def test_configured_value_never_raises_a_smaller_window(monkeypatch):
    monkeypatch.setattr(CONFIG, "max_context_tokens", 800_000, raising=False)
    _fake_registry(monkeypatch, {"o/small": _caps(max_input=128_000)})

    # A ceiling above what the model accepts must not be mistaken for a budget.
    assert resolve_context_limit("o/small") == 128_000


def test_registry_failure_does_not_break_the_budget(monkeypatch):
    def _boom():
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr("suzent.core.model_registry.get_model_registry", _boom)

    assert resolve_context_limit("g/big") == DEFAULT_CONTEXT_LIMIT_TOKENS


def test_capabilities_without_input_split_use_the_whole_window(monkeypatch):
    # Some registry entries only carry a total; the sum is then the best estimate.
    _fake_registry(monkeypatch, {"x/total-only": _caps(max_output=32_000)})

    assert resolve_context_limit("x/total-only") == 32_000


@pytest.mark.asyncio
async def test_processor_trigger_follows_the_models_window(monkeypatch):
    """Same history, two models: only the one that is actually short compacts."""
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", lambda p: None)
    monkeypatch.setattr(CONFIG, "compaction_keep_recent_turns", 3, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.80, raising=False)
    _fake_registry(
        monkeypatch,
        {
            "o/small": _caps(max_input=1_000),
            "g/big": _caps(max_input=10_000_000),
        },
    )

    # A history far too big for a 1k window and trivial for a 10M one.
    hist: list = []
    for i in range(6):
        hist.append(ModelRequest(parts=[UserPromptPart(content=f"ask {i} " * 200)]))
        hist.append(ModelResponse(parts=[TextPart(content=f"answer {i} " * 200)]))
    hist.append(ModelRequest(parts=[UserPromptPart(content="pending")]))

    async def _shrink(self, messages, **kwargs):
        return messages[:1] + messages[-2:]

    monkeypatch.setattr(
        cc.ContextCompressor, "_perform_compression", _shrink, raising=True
    )
    ctx = SimpleNamespace(
        deps=SimpleNamespace(stateless=False, chat_id="c1", user_id="u1"),
        usage=SimpleNamespace(input_tokens=0),
    )

    big = make_compaction_history_processor(model_id="g/big")
    assert await big(ctx, hist) is hist

    small = make_compaction_history_processor(model_id="o/small")
    compacted = await small(ctx, hist)
    assert len(compacted) < len(hist)
    # pydantic-ai invariant: the processed history still ends with a ModelRequest.
    assert isinstance(compacted[-1], ModelRequest)
