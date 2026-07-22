"""Regression tests: an embedding-backend failure must NEVER be silently turned
into a zero vector (which poisons the vector index and breaks retrieval). It must
raise, and the indexer must leave the index untouched + retryable on failure.
"""

import pytest

from suzent.llm import EmbeddingGenerator
from suzent.memory.indexer import CoreMemoryFileIndexer


@pytest.mark.asyncio
async def test_generate_raises_on_backend_failure(monkeypatch):
    """generate() must raise (not return a zero vector) when the backend errors."""
    gen = EmbeddingGenerator(model="ollama/nomic-embed-text", dimension=768)

    class _Boom:
        async def aembedding(self, *a, **k):
            raise RuntimeError("embedding backend unreachable")

    import suzent.llm as llm_mod

    monkeypatch.setattr(llm_mod, "_litellm", lambda: _Boom())

    with pytest.raises(Exception):
        await gen.generate("the user works at Microsoft")


@pytest.mark.asyncio
async def test_reindex_file_leaves_index_untouched_on_embed_failure():
    """_reindex_file must embed first and only mutate the store once every embedding
    succeeds — so a transient failure neither deletes existing rows nor stores poison."""
    indexer = CoreMemoryFileIndexer()

    class _BoomEmb:
        async def generate(self, text):
            raise RuntimeError("embedding backend unreachable")

    class _RecordingStore:
        def __init__(self):
            self.deleted = []
            self.added = []

        async def delete_memories_by_source_file(self, source_file, user_id):
            self.deleted.append(source_file)

        async def delete_memories_by_source_date(self, date, user_id):
            self.deleted.append(date)

        async def add_memory(self, **kwargs):
            self.added.append(kwargs)

    store = _RecordingStore()

    with pytest.raises(Exception):
        await indexer._reindex_file(
            label="notebook",
            filename="3_Personal/Work.md",
            content="# Work\n\nWorks at Microsoft on the Azure team.",
            lancedb_store=store,
            embedding_gen=_BoomEmb(),
            user_id="u",
        )

    # The index must be completely untouched: no delete, no add → fully retryable.
    assert store.deleted == [], "must not delete existing rows when embedding fails"
    assert store.added == [], "must not store any (poisoned) rows when embedding fails"
