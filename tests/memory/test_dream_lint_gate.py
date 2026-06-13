"""Tests for the dream runner's lint phase gate.

Lint is an editorial audit that runs in the SAME runner as ingest, but only once
ingest has caught up (so it never starves new-log consolidation) and only on a
weekly cadence keyed off the last `## [date] lint` entry in log.md.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from suzent.config import CONFIG
from suzent.core.dream_runner import DreamRunner


class _Store:
    def __init__(self, last_lint=None):
        self._last_lint = last_lint
        self.written = []

    def read_last_lint_date(self):
        return self._last_lint

    async def write_lint_entry(self, run_date, summary=""):
        self.written.append((run_date, summary))


class _Mgr:
    def __init__(self, last_lint=None):
        self.markdown_store = _Store(last_lint)


def _ymd(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def test_lint_due_when_never_run(monkeypatch):
    monkeypatch.setattr(CONFIG, "memory_lint_enabled", True)
    r = DreamRunner()
    assert r._lint_due(_Mgr(last_lint=None)) is True


def test_lint_not_due_within_cadence(monkeypatch):
    monkeypatch.setattr(CONFIG, "memory_lint_enabled", True)
    monkeypatch.setattr(CONFIG, "memory_lint_min_days", 7.0)
    r = DreamRunner()
    assert r._lint_due(_Mgr(last_lint=_ymd(2))) is False


def test_lint_due_after_cadence(monkeypatch):
    monkeypatch.setattr(CONFIG, "memory_lint_enabled", True)
    monkeypatch.setattr(CONFIG, "memory_lint_min_days", 7.0)
    r = DreamRunner()
    assert r._lint_due(_Mgr(last_lint=_ymd(9))) is True


def test_lint_disabled(monkeypatch):
    monkeypatch.setattr(CONFIG, "memory_lint_enabled", False)
    r = DreamRunner()
    assert r._lint_due(_Mgr(last_lint=None)) is False


def test_lint_rate_limited_after_attempt(monkeypatch):
    """Even if overdue, don't re-attempt within 24h of the last attempt."""
    monkeypatch.setattr(CONFIG, "memory_lint_enabled", True)
    monkeypatch.setattr(CONFIG, "memory_lint_min_days", 7.0)
    r = DreamRunner()
    r._last_lint_attempt_at = time.time()  # just attempted
    assert r._lint_due(_Mgr(last_lint=_ymd(30))) is False


@pytest.mark.asyncio
async def test_run_lint_records_entry_on_clean_run(monkeypatch):
    """A clean lint pass (even with no page changes) records a log entry so the
    weekly cadence advances."""
    monkeypatch.setattr(CONFIG, "memory_lint_enabled", True)
    r = DreamRunner()
    mgr = _Mgr(last_lint=None)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(r, "_reset_dream_chat", _noop)
    monkeypatch.setattr(r, "_run_lint_agent", _noop)
    monkeypatch.setattr(r, "_pause_watcher", lambda: None)
    monkeypatch.setattr(r, "_resume_watcher", lambda: None)
    # No page changes between before/after.
    monkeypatch.setattr(r, "_content_pages_state", lambda m: {"p": 1.0})

    result = await r._run_lint(mgr)

    assert result["ok"] is True
    assert result["changed"] is False
    assert len(mgr.markdown_store.written) == 1  # lint entry recorded


@pytest.mark.asyncio
async def test_run_lint_no_entry_when_agent_fails(monkeypatch):
    monkeypatch.setattr(CONFIG, "memory_lint_enabled", True)
    r = DreamRunner()
    mgr = _Mgr(last_lint=None)

    async def _noop(*a, **k):
        return None

    async def _boom(*a, **k):
        raise RuntimeError("lint agent crashed")

    monkeypatch.setattr(r, "_reset_dream_chat", _noop)
    monkeypatch.setattr(r, "_run_lint_agent", _boom)
    monkeypatch.setattr(r, "_pause_watcher", lambda: None)
    monkeypatch.setattr(r, "_resume_watcher", lambda: None)
    monkeypatch.setattr(r, "_content_pages_state", lambda m: {"p": 1.0})

    result = await r._run_lint(mgr)

    assert result["ok"] is False
    assert mgr.markdown_store.written == []  # cadence does NOT advance on failure
