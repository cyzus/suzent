"""Appending to a daily log must not re-embed the whole day.

reindex_file_now runs after every conversation turn, and the archive path used to
delete the date's rows and re-embed every fact in the file. Across the real corpus
that is ~28x more embedding calls than there are facts - quadratic in appends per
day - plus a single-row insert for each, which is what fragments the table.

The diff must not change the end state: whatever the old full replace would have
left in the index is what the diff leaves too.
"""

import pytest

from suzent.memory.indexer import CoreMemoryFileIndexer


class _FakeEmbeddings:
    model = "fake"

    def __init__(self):
        self.calls = []

    async def generate(self, text):
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


class _FakeStore:
    """Enough of the LanceDB surface for the archive path."""

    def __init__(self, rows=None, lister_raises=False):
        self.rows = list(rows or [])
        self.deleted_dates = []
        self.deleted_ids = []
        self.lister_raises = lister_raises
        self._n = 0

    async def list_source_rows(self, source_date, user_id):
        if self.lister_raises:
            raise RuntimeError("query failed")
        return [dict(r) for r in self.rows]

    async def add_memory(
        self, content, embedding, user_id, chat_id, metadata, importance
    ):
        self._n += 1
        rid = f"id-{self._n}"
        self.rows.append({"id": rid, "content": content})
        return rid

    async def delete_memory(self, memory_id):
        self.deleted_ids.append(memory_id)
        self.rows = [r for r in self.rows if r["id"] != memory_id]
        return True

    async def delete_memories_by_source_date(self, date, user_id):
        self.deleted_dates.append(date)
        self.rows = []
        return True


def _log(*facts):
    return "\n".join(f"- [preference] {f}" for f in facts)


async def _reindex(store, emb, content):
    return await CoreMemoryFileIndexer()._reindex_file(
        label="archive",
        filename="2026-08-23.md",
        content=content,
        lancedb_store=store,
        embedding_gen=emb,
        user_id="u1",
    )


@pytest.mark.asyncio
async def test_only_the_new_fact_is_embedded():
    store = _FakeStore([{"id": "a", "content": "Prefers dark mode"}])
    emb = _FakeEmbeddings()

    n = await _reindex(store, emb, _log("Prefers dark mode", "Uses Unreal Engine 5"))

    assert emb.calls == ["Uses Unreal Engine 5"]
    assert n == 2
    assert store.deleted_dates == []


@pytest.mark.asyncio
async def test_a_settled_log_costs_nothing():
    """The watcher re-checks files constantly; an unchanged day must be free."""
    store = _FakeStore([{"id": "a", "content": "Prefers dark mode"}])
    emb = _FakeEmbeddings()

    await _reindex(store, emb, _log("Prefers dark mode"))

    assert emb.calls == []
    assert store.deleted_ids == []


@pytest.mark.asyncio
async def test_rows_whose_fact_is_gone_are_dropped():
    """A tombstoned fact is filtered out of `rows`, so the diff must remove it."""
    store = _FakeStore(
        [
            {"id": "a", "content": "Prefers dark mode"},
            {"id": "b", "content": "Tombstoned fact"},
        ]
    )

    await _reindex(store, _FakeEmbeddings(), _log("Prefers dark mode"))

    assert store.deleted_ids == ["b"]
    assert [r["content"] for r in store.rows] == ["Prefers dark mode"]


@pytest.mark.asyncio
async def test_duplicate_rows_for_one_day_collapse():
    store = _FakeStore(
        [
            {"id": "a", "content": "Prefers dark mode"},
            {"id": "b", "content": "prefers   dark mode"},
        ]
    )

    await _reindex(store, _FakeEmbeddings(), _log("Prefers dark mode"))

    assert store.deleted_ids == ["b"]


@pytest.mark.asyncio
async def test_first_index_of_a_day_uses_the_full_path():
    """Nothing indexed yet means the diff is the whole file; don't pay for the query."""
    store = _FakeStore([])
    emb = _FakeEmbeddings()

    n = await _reindex(store, emb, _log("Prefers dark mode", "Uses Unreal Engine 5"))

    assert n == 2
    assert len(emb.calls) == 2
    assert store.deleted_dates == ["2026-08-23"]


@pytest.mark.asyncio
async def test_a_failed_diff_falls_back_to_full_replace():
    """Degrading to more work is fine; degrading to a wrong index is not."""
    store = _FakeStore(
        [{"id": "a", "content": "Prefers dark mode"}], lister_raises=True
    )
    emb = _FakeEmbeddings()

    n = await _reindex(store, emb, _log("Prefers dark mode", "Uses Unreal Engine 5"))

    assert n == 2
    assert len(emb.calls) == 2
    assert store.deleted_dates == ["2026-08-23"]


@pytest.mark.asyncio
async def test_notebook_pages_still_replace_wholesale():
    """Vault pages are rewritten in place, so a diff would buy nothing."""
    store = _FakeStore([{"id": "a", "content": "old paragraph"}])
    emb = _FakeEmbeddings()

    async def _no(*a, **k):
        raise AssertionError("archive-only path used for a notebook page")

    store.list_source_rows = _no

    async def _del_file(f, u):
        return True

    store.delete_memories_by_source_file = _del_file

    n = await CoreMemoryFileIndexer()._reindex_file(
        label="notebook",
        filename="3_Personal/Suzy.md",
        content="a new paragraph",
        lancedb_store=store,
        embedding_gen=emb,
        user_id="u1",
    )

    assert n == 1
