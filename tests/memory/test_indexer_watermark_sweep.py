"""A consolidated log must leave the index even if this indexer never wrote it.

Archive logs at or below the watermark have been folded into the vault, so their
rows are dropped from the search index and never re-added. The drop used to fire
only for a file already present in `_mtimes` — but `_mtimes` is emptied by a state
version bump or a failed load, and rows written by an older chunking scheme are not
in it to begin with. Those rows were then stranded: never swept, never rewritten,
and never reachable by a reindex.
"""

import json

import pytest

from suzent.memory.indexer import CoreMemoryFileIndexer
from suzent.memory.markdown_store import MarkdownMemoryStore


@pytest.fixture
def store(tmp_path):
    store = MarkdownMemoryStore(
        base_dir=tmp_path / "memory", notebook_dir=tmp_path / "notebook"
    )
    (store.notebook_dir / "log.md").write_text(
        "## [2026-06-30] ingest | daily logs  watermark=2026-06-30\n",
        encoding="utf-8",
    )
    return store


class _FakeStore:
    def __init__(self):
        self.deleted_dates = []

    async def delete_memories_by_source_date(self, date, user_id):
        self.deleted_dates.append(date)
        return 1


class _FakeEmbeddings:
    model = "fake"

    async def generate(self, text):
        return [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_orphaned_pre_watermark_rows_are_swept(store):
    """No `_mtimes` entry — the case that used to strand rows forever."""
    (store.archive_dir / "2026-05-03.md").write_text("- [goal] x\n", encoding="utf-8")
    indexer = CoreMemoryFileIndexer()
    indexer._load_state(store)
    indexer._mtimes.clear()
    lancedb = _FakeStore()

    await indexer._check_and_update_impl(store, lancedb, _FakeEmbeddings(), "u")

    assert lancedb.deleted_dates == ["2026-05-03"]


@pytest.mark.asyncio
async def test_a_log_is_swept_only_once(store):
    """The sweep is a delete against the whole date; repeating it every pass would
    be a table scan per startup for nothing."""
    (store.archive_dir / "2026-05-03.md").write_text("- [goal] x\n", encoding="utf-8")
    indexer = CoreMemoryFileIndexer()
    indexer._load_state(store)
    lancedb = _FakeStore()

    await indexer._check_and_update_impl(store, lancedb, _FakeEmbeddings(), "u")
    await indexer._check_and_update_impl(store, lancedb, _FakeEmbeddings(), "u")

    assert lancedb.deleted_dates == ["2026-05-03"]


@pytest.mark.asyncio
async def test_swept_survives_a_restart(store):
    """Persisted, or every restart re-runs every historical delete."""
    (store.archive_dir / "2026-05-03.md").write_text("- [goal] x\n", encoding="utf-8")
    first = CoreMemoryFileIndexer()
    first._load_state(store)
    await first._check_and_update_impl(store, _FakeStore(), _FakeEmbeddings(), "u")

    payload = json.loads(
        (store.base_dir / CoreMemoryFileIndexer.INDEX_STATE_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert "archive:2026-05-03.md" in payload["swept"]

    second = CoreMemoryFileIndexer()
    second._load_state(store)
    lancedb = _FakeStore()
    await second._check_and_update_impl(store, lancedb, _FakeEmbeddings(), "u")

    assert lancedb.deleted_dates == []


@pytest.mark.asyncio
async def test_post_watermark_logs_are_untouched(store):
    (store.archive_dir / "2026-07-01.md").write_text("- [goal] x\n", encoding="utf-8")
    indexer = CoreMemoryFileIndexer()
    indexer._load_state(store)
    indexer._mtimes.clear()
    lancedb = _FakeStore()

    await indexer._check_and_update_impl(store, lancedb, _FakeEmbeddings(), "u")

    # The log is indexed, not swept: it is still the live copy of that day.
    assert "archive:2026-07-01.md" not in indexer._swept
