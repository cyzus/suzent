"""Regression tests for the dream runner's watermark advance (review finding #1).

The watermark must advance ONLY when the consolidation agent finished cleanly AND
produced real page changes. A failed or timed-out run can leave a partially-written
page; advancing on "a page changed" alone would mark the whole batch consolidated and
let the indexer drop the raw daily logs for facts that were never folded into the
vault (silent data loss — the exact class of bug this PR exists to kill).
"""
import asyncio

import pytest

from suzent.core import dream_runner as dr_mod
from suzent.core.dream_runner import DreamRunner


class _FakeMarkdownStore:
    def read_watermark(self):
        return "2026-06-01"


class _FakeIndexer:
    async def check_and_update(self, **kwargs):
        return {}


class _FakeManager:
    def __init__(self):
        self.markdown_store = _FakeMarkdownStore()
        self.llm_client = object()
        self.store = object()
        self.embedding_gen = object()
        self._core_indexer = _FakeIndexer()

    async def promote_memory_md(self, user_id):
        return None


async def _anoop(*a, **k):
    return None


def _wire(runner, monkeypatch, mgr, *, page_states, agent):
    """Wire a DreamRunner with deterministic stand-ins. page_states is the sequence
    of mtime snapshots returned by _content_pages_state (before, after)."""
    monkeypatch.setattr(dr_mod, "get_memory_manager", lambda: mgr)
    monkeypatch.setattr(runner, "_pending_dates", lambda m, wm: ["2026-06-02", "2026-06-03"])
    monkeypatch.setattr(runner, "_reset_dream_chat", _anoop)
    monkeypatch.setattr(runner, "_pause_watcher", lambda: None)
    monkeypatch.setattr(runner, "_resume_watcher", lambda: None)
    monkeypatch.setattr(runner, "_run_agent", agent)

    snaps = iter(page_states)
    monkeypatch.setattr(runner, "_content_pages_state", lambda m: next(snaps))

    advanced = []

    async def _advance(m, w_new):
        advanced.append(w_new)

    monkeypatch.setattr(runner, "_advance_watermark", _advance)
    return advanced


@pytest.mark.asyncio
async def test_watermark_not_advanced_when_agent_fails_after_partial_write(monkeypatch):
    """Agent times out *after* changing one page → watermark must stay put."""
    runner = DreamRunner()

    async def boom(start, end):
        raise asyncio.TimeoutError("dream agent timed out mid-write")

    # before != after: a page WAS changed (the partial write), but the agent failed.
    advanced = _wire(
        runner, monkeypatch, _FakeManager(),
        page_states=[{"p": 1.0}, {"p": 2.0}], agent=boom,
    )

    result = await runner.force_run()

    assert advanced == [], "must NOT advance the watermark when the agent failed"
    assert result["advanced"] is False
    assert result["watermark"] == "2026-06-01"  # unchanged
    # The batch is flagged for retry so it is re-attempted, not silently lost.
    assert runner._failures.get("2026-06-03", 0) == 1


@pytest.mark.asyncio
async def test_watermark_not_advanced_when_agent_succeeds_but_no_change(monkeypatch):
    """Clean run that produced no page changes → no advance (unchanged behavior)."""
    runner = DreamRunner()
    advanced = _wire(
        runner, monkeypatch, _FakeManager(),
        page_states=[{"p": 1.0}, {"p": 1.0}], agent=_anoop,
    )

    result = await runner.force_run()

    assert advanced == []
    assert result["advanced"] is False
    assert runner._failures.get("2026-06-03", 0) == 1


@pytest.mark.asyncio
async def test_watermark_advances_on_clean_run_with_changes(monkeypatch):
    """Agent finished cleanly AND a page changed → watermark advances (happy path)."""
    runner = DreamRunner()
    advanced = _wire(
        runner, monkeypatch, _FakeManager(),
        page_states=[{"p": 1.0}, {"p": 2.0}], agent=_anoop,
    )

    result = await runner.force_run()

    assert advanced == ["2026-06-03"]
    assert result["advanced"] is True
    assert result["changed"] is True
    assert "2026-06-03" not in runner._failures
