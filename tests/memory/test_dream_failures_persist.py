"""The dream's retry counter must survive a process restart.

Retry-then-skip exists so one un-consolidatable batch cannot wedge the backlog
forever. The runner attempts a given batch at most once per app run, so a counter
held only in memory never reaches ``max_retries`` on a desktop app that restarts
between attempts — the skip never fires and the watermark stops advancing for good.
"""

import json

import pytest

from suzent.core.dream_runner import DreamRunner
from suzent.memory.markdown_store import MarkdownMemoryStore


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path / "memory", notebook_dir=tmp_path / "notebook"
    )


class _FakeManager:
    def __init__(self, markdown_store):
        self.markdown_store = markdown_store


def test_failures_roundtrip_through_disk(store):
    assert store.read_dream_failures() == {}

    store.write_dream_failures({"2026-03-25": 2})

    assert store.read_dream_failures() == {"2026-03-25": 2}
    assert json.loads(store.dream_state_path.read_text(encoding="utf-8")) == {
        "failures": {"2026-03-25": 2}
    }


def test_counter_survives_a_new_runner_instance(store):
    """A fresh process must see the count a previous one recorded."""
    mgr = _FakeManager(store)

    first = DreamRunner()
    first._load_failures(mgr)
    first._failures["2026-03-25"] = first._failures.get("2026-03-25", 0) + 1
    first._save_failures(mgr)

    second = DreamRunner()  # stands in for the next app launch
    second._load_failures(mgr)

    assert second._failures == {"2026-03-25": 1}


def test_hydration_happens_once_per_process(store):
    """Later disk writes must not clobber counters the live runner is mutating."""
    mgr = _FakeManager(store)
    runner = DreamRunner()
    runner._load_failures(mgr)
    runner._failures["2026-03-25"] = 3

    store.write_dream_failures({"2026-03-25": 0})
    runner._load_failures(mgr)

    assert runner._failures == {"2026-03-25": 3}


def test_unreadable_state_degrades_to_empty(store):
    store.dream_state_path.write_text("{not json", encoding="utf-8")

    assert store.read_dream_failures() == {}


def test_malformed_state_shapes_are_ignored(store):
    store.dream_state_path.write_text(
        json.dumps({"failures": {"2026-03-25": "three"}}), encoding="utf-8"
    )

    assert store.read_dream_failures() == {}
