"""The dream retires duplicate log facts by tombstone, not by rewriting logs.

Step 3b used to resolve a duplicate by doing nothing, which is why a fact written
64 times stayed in the index 64 times. The dream now hands the runner the lines it
folded into the vault; the runner tombstones them and reindexes the days they came
from. That last part is load-bearing: appending a tombstone does not change the
log's mtime, so the mtime watcher never revisits those days on its own.
"""

import pytest

from suzent.core.dream_runner import DreamRunner
from suzent.memory import memory_context
from suzent.memory.markdown_store import MarkdownMemoryStore

FACT = "The user wants to be reminded to drink water hourly from 9 AM to 9 PM."


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=str(tmp_path / "memory"), notebook_dir=str(tmp_path / "notebook")
    )


class _FakeIndexer:
    def __init__(self):
        self.reindexed = []

    async def reindex_file_now(self, **kwargs):
        self.reindexed.append((kwargs["label"], kwargs["filename"]))
        return 1


class _FakeManager:
    def __init__(self, markdown_store):
        self.markdown_store = markdown_store
        self._core_indexer = _FakeIndexer()
        self.store = None
        self.embedding_gen = None


def _log(store, date, *lines):
    (store.archive_dir / f"{date}.md").write_text(
        "".join(f"- [preference] {ln}\n" for ln in lines), encoding="utf-8"
    )


# --- prompt ---


def test_duplicate_rule_no_longer_says_do_nothing():
    roots = memory_context.resolve_dream_roots(sandbox_enabled=True)
    text = memory_context.build_dream_instructions(
        roots,
        start="2026-01-01",
        end="2026-01-02",
        confirmations="   (none pending)",
        revisits="   (none due)",
    )

    assert "-> do nothing" not in text
    assert roots.superseded_path in text


# --- store ---


def test_superseded_reads_back_deduped_and_unbulleted(store):
    store.superseded_path.write_text(
        f"- {FACT}\n{FACT}\n\n  \nSomething else entirely, at length.\n",
        encoding="utf-8",
    )

    assert store.read_superseded() == [FACT, "Something else entirely, at length."]


def test_archive_dates_containing_finds_every_day(store):
    _log(store, "2026-03-10", FACT)
    _log(store, "2026-03-11", "Unrelated fact about the build system.")
    _log(store, "2026-03-12", f"  {FACT.upper()}")

    assert store.archive_dates_containing([FACT]) == ["2026-03-10", "2026-03-12"]
    assert store.archive_dates_containing([]) == []


# --- runner ---


@pytest.mark.asyncio
async def test_retire_tombstones_and_reindexes_each_day(store):
    _log(store, "2026-03-10", FACT)
    _log(store, "2026-03-12", FACT)
    store.superseded_path.write_text(FACT + "\n", encoding="utf-8")
    mgr = _FakeManager(store)

    n = await DreamRunner()._retire_superseded(mgr)

    assert n == 1
    assert store.is_tombstoned(FACT)
    assert mgr._core_indexer.reindexed == [
        ("archive", "2026-03-10.md"),
        ("archive", "2026-03-12.md"),
    ]
    assert store.read_superseded() == []


@pytest.mark.asyncio
async def test_short_lines_are_refused(store):
    """A generic fragment would substring-match unrelated logs; drop it instead."""
    _log(store, "2026-03-10", "dark mode")
    store.superseded_path.write_text("dark mode\n", encoding="utf-8")
    mgr = _FakeManager(store)

    assert await DreamRunner()._retire_superseded(mgr) == 0
    assert not store.is_tombstoned("dark mode")
    assert mgr._core_indexer.reindexed == []


@pytest.mark.asyncio
async def test_empty_handoff_is_a_no_op(store):
    mgr = _FakeManager(store)

    assert await DreamRunner()._retire_superseded(mgr) == 0
    assert mgr._core_indexer.reindexed == []


@pytest.mark.asyncio
async def test_handoff_is_cleared_only_after_tombstoning(store):
    """A crash mid-run must replay, not silently drop the lines."""
    _log(store, "2026-03-10", FACT)
    store.superseded_path.write_text(FACT + "\n", encoding="utf-8")
    mgr = _FakeManager(store)

    async def boom(**kwargs):
        raise RuntimeError("lancedb down")

    mgr._core_indexer.reindex_file_now = boom

    await DreamRunner()._retire_superseded(mgr)

    # The tombstone is durable, so the row is filtered on any future rebuild even
    # though this run's explicit reindex failed.
    assert store.is_tombstoned(FACT)
