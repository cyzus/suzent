"""Regression test for universal tombstones (review finding #2).

Deleting a notebook/core memory tombstones its content. Before the fix the indexer
applied tombstones only to archive (diary) facts, so notebook/core chunks were
re-indexed unconditionally — a user could delete a notebook memory, get
``{"success": true}``, then ``/memory/reindex {"clear_existing": true}`` would
resurrect it. The fix applies the same normalized-content tombstone filter to
notebook/core chunks, so a deletion is durable across a full rebuild.
"""
import pytest

from suzent.memory.indexer import CoreMemoryFileIndexer


class _FixedEmb:
    async def generate(self, text):
        return [0.1, 0.2, 0.3]


class _RecordingStore:
    def __init__(self):
        self.added = []

    async def delete_memories_by_source_file(self, source_file, user_id):
        pass

    async def delete_memories_by_source_date(self, date, user_id):
        pass

    async def add_memory(self, **kwargs):
        self.added.append(kwargs)


async def _reindex(content, tombstones):
    indexer = CoreMemoryFileIndexer()
    store = _RecordingStore()
    await indexer._reindex_file(
        label="notebook",
        filename="3_Personal/Work.md",
        content=content,
        lancedb_store=store,
        embedding_gen=_FixedEmb(),
        user_id="u",
        tombstones=tombstones,
    )
    return store.added


@pytest.mark.asyncio
async def test_tombstoned_notebook_chunk_is_not_reindexed():
    page = "Alice works at Microsoft on the Azure team and ships weekly."
    normalized = " ".join(page.lower().split())

    # Control: without a tombstone, the chunk indexes normally.
    added = await _reindex(page, set())
    assert any("Microsoft" in row["content"] for row in added)

    # With the tombstone, the chunk must be skipped — no resurrection on rebuild.
    added = await _reindex(page, {normalized})
    assert added == [], "tombstoned notebook chunk must not be re-indexed"
