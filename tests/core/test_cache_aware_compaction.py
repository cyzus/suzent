"""Compaction that knows how long the provider keeps its prompt cache: when a
prepared summary is applied early, and which model writes a summary."""

import asyncio
import json
import time
import dataclasses
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

import suzent.core.cache_ttl as cache_ttl
import suzent.core.context_compressor as cc
from suzent.config import CONFIG
from suzent.core import model_factory
from suzent.core.context_compressor import (
    ContextCompressor,
    make_compaction_history_processor,
    schedule_precompaction,
)
from suzent.core.prompt_cache import latest_request

from .test_cached_compaction import SUMMARY, _agent, _long_history, _run


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", lambda p: None)
    monkeypatch.setattr(CONFIG, "compaction_keep_recent_turns", 1, raising=False)
    monkeypatch.setattr(CONFIG, "compaction_reuse_prompt_cache", True, raising=False)
    monkeypatch.setattr(CONFIG, "context_precompaction_trigger", 0.50, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.80, raising=False)
    monkeypatch.setattr(CONFIG, "memory_enabled", False, raising=False)
    # _long_history() is ~6k tokens: 60% of this window.
    monkeypatch.setattr(CONFIG, "max_context_tokens", 10_000, raising=False)
    monkeypatch.setattr(cache_ttl, "_store_path", lambda: tmp_path / "ttl.json")
    monkeypatch.setattr(cache_ttl, "_observed", None)
    monkeypatch.setattr(cache_ttl, "_last_request_at", {})
    cc.reset_compaction_suppression()
    cc.discard_precompaction()
    yield
    cc.reset_compaction_suppression()
    cc.discard_precompaction()


# ── TTL estimate ─────────────────────────────────────────────────────────────


def test_anthropic_ttl_follows_the_requested_breakpoints() -> None:
    assert (
        cache_ttl.default_ttl_seconds("anthropic/x", {"anthropic_cache": True}) == 300
    )
    assert (
        cache_ttl.default_ttl_seconds("anthropic/x", {"anthropic_cache_messages": "1h"})
        == 3600
    )
    assert cache_ttl.default_ttl_seconds("deepseek/deepseek-chat") == 3600
    assert cache_ttl.estimate_ttl_seconds("ollama/llama3") is None


def test_one_hour_cache_is_requested_on_every_breakpoint(monkeypatch) -> None:
    monkeypatch.setattr(CONFIG, "anthropic_prompt_cache_ttl", "1h", raising=False)
    assert set(model_factory.anthropic_cache_settings(None).values()) == {"1h"}
    monkeypatch.setattr(CONFIG, "anthropic_prompt_cache_ttl", "5m", raising=False)
    assert set(model_factory.anthropic_cache_settings(None).values()) == {True}


def test_a_hit_after_a_long_idle_raises_the_estimate(tmp_path) -> None:
    now = 1_000_000.0
    cache_ttl.observe_request("openai/gpt-x", now, 0)
    cache_ttl.observe_request("openai/gpt-x", now + 1800, 5000)

    assert cache_ttl.estimate_ttl_seconds("openai/gpt-x") == 1800
    assert json.loads((tmp_path / "ttl.json").read_text()) == {"openai/gpt-x": 1800}

    # A later miss does not lower it; the prefix may simply have changed.
    cache_ttl.observe_request("openai/gpt-x", now + 9000, 0)
    assert cache_ttl.estimate_ttl_seconds("openai/gpt-x") == 1800


def test_short_gaps_and_small_reads_teach_nothing() -> None:
    now = 1_000_000.0
    cache_ttl.observe_request("moonshot/kimi", now, 0)
    cache_ttl.observe_request("moonshot/kimi", now + 30, 50_000)
    cache_ttl.observe_request("moonshot/kimi", now + 4000, 200)

    assert cache_ttl.estimate_ttl_seconds("moonshot/kimi") is None


async def test_recorded_request_carries_the_model_and_send_time() -> None:
    sent: list = []
    agent = _agent(sent, [], model_id="openai/gpt-x")
    before = time.time()
    await _run(agent, "recorded")

    snapshot = latest_request("recorded")
    assert snapshot.model_id == "openai/gpt-x"
    assert snapshot.sent_at >= before


async def test_a_summary_request_counts_as_a_cache_refresh() -> None:
    sent: list = []
    agent = _agent(sent, [f"<summary>{SUMMARY}</summary>"], model_id="openai/gpt-x")
    history = await _run(agent, "refreshed")
    first = latest_request("refreshed").sent_at

    assert await cc.summarize_on_cached_prefix("refreshed", history, 1, 200_000)

    assert latest_request("refreshed").sent_at > first


# ── Applying the prepared summary once the cache has expired ─────────────────


def _stub_summaries(monkeypatch) -> list:
    asked: list = []

    async def fake(self, messages, end_index, focus=None):
        asked.append(end_index)
        return SUMMARY

    monkeypatch.setattr(ContextCompressor, "_summarize_history", fake)
    return asked


def _last_request(monkeypatch, model_id: str, idle: float) -> None:
    snapshot = SimpleNamespace(
        model_id=model_id, settings={}, sent_at=time.time() - idle, messages=()
    )
    monkeypatch.setattr(
        "suzent.core.prompt_cache.latest_request", lambda chat_id: snapshot
    )


async def _resume(chat_id: str, history: list) -> list:
    next_turn = history + [ModelRequest(parts=[UserPromptPart(content="back")])]
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id=chat_id, user_id="u"))
    return next_turn, await make_compaction_history_processor()(ctx, next_turn)


async def test_cold_cache_applies_the_prepared_summary_early(monkeypatch) -> None:
    _stub_summaries(monkeypatch)
    history = _long_history()
    assert schedule_precompaction("cold", history)
    await asyncio.sleep(0)
    _last_request(monkeypatch, "openai/gpt-x", idle=900)

    sent, out = await _resume("cold", history)

    assert len(out) < len(sent)
    assert SUMMARY in out[2].parts[0].content
    assert "cold" not in cc._PRECOMPACTIONS


async def test_cold_cache_notice_says_why_and_keeps_the_summary(monkeypatch) -> None:
    events: list = []
    monkeypatch.setattr(
        "suzent.core.stream_registry.emit_bus_event", lambda p: events.append(p)
    )
    persisted: list = []
    monkeypatch.setattr(
        cc, "persist_compaction_notice", lambda **kw: persisted.append(kw)
    )
    _stub_summaries(monkeypatch)
    history = _long_history()
    assert schedule_precompaction("why", history)
    await asyncio.sleep(0)
    _last_request(monkeypatch, "openai/gpt-x", idle=900)

    await _resume("why", history)
    await asyncio.sleep(0)

    prep = [e["stage"] for e in events if e["event"] == "precompaction"]
    assert prep == ["start", "ready"]
    complete = next(
        e
        for e in events
        if e["event"] == "auto_compaction" and e["stage"] == "complete"
    )
    assert complete["reason"] == "cold_cache"
    assert 890 <= complete["idle_seconds"] <= 910
    assert complete["summary"] == SUMMARY
    (notice,) = persisted
    assert notice["details"]["reason"] == "cold_cache"
    assert notice["details"]["summary"] == SUMMARY


async def test_prepared_summary_at_the_trigger_is_marked_prepared(monkeypatch) -> None:
    events: list = []
    monkeypatch.setattr(
        "suzent.core.stream_registry.emit_bus_event", lambda p: events.append(p)
    )
    monkeypatch.setattr(cc, "persist_compaction_notice", lambda **kw: None)
    monkeypatch.setattr(CONFIG, "max_context_tokens", 7_500, raising=False)
    _stub_summaries(monkeypatch)
    history = _long_history()
    assert schedule_precompaction("trigger", history)
    await asyncio.sleep(0)

    await _resume("trigger", history + [ModelResponse(parts=[TextPart("y " * 200)])])

    complete = next(
        e
        for e in events
        if e["event"] == "auto_compaction" and e["stage"] == "complete"
    )
    assert complete["reason"] == "prepared"
    assert "idle_seconds" not in complete


@pytest.mark.parametrize(
    ("model_id", "idle"),
    [("openai/gpt-x", 60), ("ollama/llama3", 7200)],
    ids=["cache still warm", "cache lifetime unknown"],
)
async def test_full_history_is_kept_otherwise(monkeypatch, model_id, idle) -> None:
    _stub_summaries(monkeypatch)
    history = _long_history()
    assert schedule_precompaction("warm", history)
    await asyncio.sleep(0)
    _last_request(monkeypatch, model_id, idle=idle)

    sent, out = await _resume("warm", history)

    assert out == sent
    assert "warm" in cc._PRECOMPACTIONS


async def test_cold_cache_without_a_prepared_summary_writes_none(monkeypatch) -> None:
    asked = _stub_summaries(monkeypatch)
    _last_request(monkeypatch, "openai/gpt-x", idle=900)

    sent, out = await _resume("nothing-prepared", _long_history())

    assert out == sent
    assert asked == []


async def test_summary_is_rewritten_once_the_tail_outgrows_it(monkeypatch) -> None:
    asked = _stub_summaries(monkeypatch)
    history = _long_history()
    assert schedule_precompaction("refresh", history)
    await asyncio.sleep(0)

    short = history + [
        ModelResponse(parts=[TextPart("ok")]),
        ModelRequest(parts=[UserPromptPart(content="a")]),
    ]
    assert not schedule_precompaction("refresh", short)

    long = short + [
        ModelResponse(parts=[TextPart("z " * 5000)]),
        ModelRequest(parts=[UserPromptPart(content="b")]),
    ]
    assert schedule_precompaction("refresh", long)
    await asyncio.sleep(0)
    assert len(asked) == 2


# ── Choosing who writes the summary ──────────────────────────────────────────


def _prices(monkeypatch, prices: dict) -> None:
    monkeypatch.setattr(
        "suzent.core.cost_tracker.estimate_cost_usd",
        lambda model, **_: prices.get(model),
    )


def _compressor() -> ContextCompressor:
    return ContextCompressor(
        llm_client=SimpleNamespace(model="openai/cheap"), chat_id="route"
    )


def test_warm_cache_keeps_the_conversations_model(monkeypatch) -> None:
    _last_request(monkeypatch, "anthropic/big", idle=30)
    _prices(monkeypatch, {"anthropic/big": 1.0, "openai/cheap": 0.01})

    assert _compressor()._prefer_cached_prefix(_long_history(), 5)


@pytest.mark.parametrize(
    ("prices", "cached"),
    [
        ({"anthropic/big": 1.0, "openai/cheap": 0.01}, False),
        ({"anthropic/big": 0.01, "openai/cheap": 1.0}, True),
        ({"openai/cheap": 0.01}, True),
    ],
    ids=["extraction cheaper", "conversation cheaper", "unpriced"],
)
def test_cold_cache_picks_the_cheaper_writer(monkeypatch, prices, cached) -> None:
    _last_request(monkeypatch, "anthropic/big", idle=900)
    _prices(monkeypatch, prices)

    assert _compressor()._prefer_cached_prefix(_long_history(), 5) is cached


def test_persisted_notice_records_when_it_happened(monkeypatch) -> None:
    stored: list = []
    db = SimpleNamespace(append_chat_message=lambda chat_id, row: stored.append(row))
    monkeypatch.setattr("suzent.database.get_database", lambda: db)

    cc.persist_compaction_notice(
        chat_id="stamped", stage="complete", source="auto", tokens_before=9000
    )

    (row,) = stored
    assert time.time() - datetime.fromisoformat(row["timestamp"]).timestamp() < 5


# ── Thresholds by size ───────────────────────────────────────────────────────


def test_large_windows_compact_at_a_fixed_size(monkeypatch) -> None:
    monkeypatch.setattr(CONFIG, "context_compaction_trigger_tokens", 200_000)
    monkeypatch.setattr(CONFIG, "context_precompaction_trigger_tokens", 100_000)

    assert cc.compaction_trigger_tokens(1_000_000) == 200_000
    assert cc.precompaction_trigger_tokens(1_000_000) == 100_000
    # A small window still uses the share, which comes first.
    assert cc.compaction_trigger_tokens(128_000) == 102_400
    assert cc.precompaction_trigger_tokens(128_000) == 64_000

    monkeypatch.setattr(CONFIG, "context_compaction_trigger_tokens", 0)
    assert cc.compaction_trigger_tokens(1_000_000) == 800_000
    monkeypatch.setattr(CONFIG, "context_precompaction_trigger", 0)
    assert cc.precompaction_trigger_tokens(1_000_000) is None


# ── Preparing the summary during a run ───────────────────────────────────────


@pytest.mark.parametrize(
    ("idle", "prepared"), [(30, True), (900, False)], ids=["warm", "cold"]
)
async def test_a_run_past_the_prewrite_size_starts_the_summary(
    monkeypatch, idle, prepared
) -> None:
    asked = _stub_summaries(monkeypatch)
    _last_request(monkeypatch, "openai/gpt-x", idle=idle)

    sent, out = await _resume("midrun", _long_history())
    await asyncio.sleep(0)

    assert out == sent
    assert ("midrun" in cc._PRECOMPACTIONS) is prepared
    assert len(asked) == int(prepared)


async def test_a_failed_summary_waits_for_the_history_to_grow(monkeypatch) -> None:
    attempts: list = []

    async def failing(self, messages, end_index, focus=None):
        attempts.append(end_index)
        raise RuntimeError("provider down")

    monkeypatch.setattr(ContextCompressor, "_summarize_history", failing)
    history = _long_history()
    assert schedule_precompaction("flaky", history)
    await asyncio.sleep(0)

    longer = history + [
        ModelResponse(parts=[TextPart("ok")]),
        ModelRequest(parts=[UserPromptPart(content="a")]),
    ]
    assert not schedule_precompaction("flaky", longer)
    assert len(attempts) == 1


# ── Keeping the prepared summary across a restart ────────────────────────────


async def test_prepared_summary_survives_a_restart(monkeypatch, temp_db) -> None:
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    temp_db.create_chat("restart", {}, chat_id="restart")
    _stub_summaries(monkeypatch)
    history = _long_history()
    assert schedule_precompaction("restart", history)
    for _ in range(50):
        await asyncio.sleep(0.01)
        if temp_db.get_prepared_summary("restart") is not None:
            break
    assert temp_db.get_prepared_summary("restart").summary == SUMMARY

    # A new process: nothing in memory, no request recorded, and the last
    # reply came in well past the provider's cache lifetime.
    cc.discard_precompaction()
    monkeypatch.setattr("suzent.core.prompt_cache.latest_request", lambda chat_id: None)
    last = (
        len(history)
        - 1
        - next(
            i for i, m in enumerate(reversed(history)) if isinstance(m, ModelResponse)
        )
    )
    history[last] = dataclasses.replace(
        history[last], timestamp=datetime.now(timezone.utc) - timedelta(minutes=15)
    )
    next_turn = history + [ModelRequest(parts=[UserPromptPart(content="back")])]
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="restart", user_id="u"))
    out = await make_compaction_history_processor(model_id="openai/gpt-x")(
        ctx, next_turn
    )

    assert len(out) < len(next_turn)
    assert SUMMARY in out[2].parts[0].content
    assert temp_db.get_prepared_summary("restart") is None
