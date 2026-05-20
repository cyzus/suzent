"""Tests for memory deduplication behavior on near-matches.

Issue #34: previously, when a newly extracted fact's cosine similarity to an
existing memory exceeded the threshold, the manager appended the existing id
to ``memories_updated`` but did **not** call any update API — silently
dropping the new content. These tests pin down that:

  * Near-match → the LanceDB store's ``update_memory`` is called with the
    new content, a freshly generated embedding, and the new metadata.
  * Below-threshold → a new memory is inserted.
  * The dedup threshold is configurable per ``MemoryManager`` instance.
  * If the store's update fails, the manager falls back to inserting so we
    never lose the fact silently.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from suzent.memory.manager import (
    DEFAULT_DEDUPLICATION_SIMILARITY_THRESHOLD,
    MemoryManager,
)
from suzent.memory.models import ExtractedFact, MemoryExtractionResult


def _make_fact(content: str = "I work at Microsoft") -> ExtractedFact:
    return ExtractedFact(
        content=content,
        importance=0.8,
        category="personal",
        tags=["job"],
        context_user_intent="share employer",
        context_agent_actions_summary="recorded employer",
        context_outcome="stored",
    )


def _make_manager(*, dedup_threshold: float | None = None) -> MemoryManager:
    """Build a MemoryManager with all I/O surfaces mocked.

    Bypasses ``__init__`` because constructing ``EmbeddingGenerator`` /
    ``LLMClient`` requires litellm configuration that's irrelevant here.
    """
    manager = MemoryManager.__new__(MemoryManager)
    manager.store = MagicMock()
    manager.store.update_memory = AsyncMock(return_value=True)
    manager.store.add_memory = AsyncMock(return_value="new-memory-id")
    manager.markdown_store = None
    manager.embedding_gen = MagicMock()
    manager.embedding_gen.generate = AsyncMock(return_value=[0.1, 0.2, 0.3])
    manager.llm_extraction_model = None
    manager.llm_client = None
    manager.wiki_manager = None
    manager.dedup_threshold = (
        dedup_threshold
        if dedup_threshold is not None
        else DEFAULT_DEDUPLICATION_SIMILARITY_THRESHOLD
    )
    return manager


def _patch_search(manager: MemoryManager, hits: list[dict[str, Any]]) -> AsyncMock:
    """Stub ``search_memories`` to return the given hits."""
    search = AsyncMock(return_value=hits)
    manager.search_memories = search  # type: ignore[assignment]
    return search


async def test_near_duplicate_actually_updates_existing_memory():
    """The data-loss bug: previously this case silently dropped new content."""
    manager = _make_manager()
    _patch_search(
        manager,
        [{"id": "existing-id", "similarity": 0.95, "content": "I work at Google"}],
    )

    result = MemoryExtractionResult.empty()
    fact = _make_fact("I work at Microsoft")
    await manager._deduplicate_and_store_facts(
        facts=[fact], user_id="u1", source_chat_id="c1", result=result
    )

    # The store's update_memory must be called with the *new* content and a
    # freshly generated embedding.
    manager.store.update_memory.assert_awaited_once()
    update_kwargs = manager.store.update_memory.await_args.kwargs
    assert update_kwargs["memory_id"] == "existing-id"
    assert update_kwargs["content"] == "I work at Microsoft"
    assert update_kwargs["embedding"] == [0.1, 0.2, 0.3]
    assert update_kwargs["importance"] == 0.8

    # No new memory inserted.
    manager.store.add_memory.assert_not_awaited()

    assert result.memories_updated == ["existing-id"]
    assert result.memories_created == []


async def test_below_threshold_inserts_new_memory():
    manager = _make_manager()
    _patch_search(
        manager,
        [{"id": "existing-id", "similarity": 0.40, "content": "loves cats"}],
    )

    result = MemoryExtractionResult.empty()
    fact = _make_fact("I work at Microsoft")
    await manager._deduplicate_and_store_facts(
        facts=[fact], user_id="u1", source_chat_id="c1", result=result
    )

    manager.store.update_memory.assert_not_awaited()
    manager.store.add_memory.assert_awaited_once()
    assert result.memories_created == ["new-memory-id"]
    assert result.memories_updated == []


async def test_no_similar_memories_inserts_new_memory():
    manager = _make_manager()
    _patch_search(manager, [])

    result = MemoryExtractionResult.empty()
    await manager._deduplicate_and_store_facts(
        facts=[_make_fact()], user_id="u1", source_chat_id="c1", result=result
    )

    manager.store.update_memory.assert_not_awaited()
    manager.store.add_memory.assert_awaited_once()
    assert result.memories_created == ["new-memory-id"]


async def test_threshold_is_configurable_per_instance():
    """A tighter threshold (e.g. 0.99) lets the same 0.95 hit be treated as new."""
    manager = _make_manager(dedup_threshold=0.99)
    _patch_search(
        manager,
        [{"id": "existing-id", "similarity": 0.95, "content": "near-match"}],
    )

    result = MemoryExtractionResult.empty()
    await manager._deduplicate_and_store_facts(
        facts=[_make_fact()], user_id="u1", source_chat_id="c1", result=result
    )

    manager.store.update_memory.assert_not_awaited()
    manager.store.add_memory.assert_awaited_once()
    assert result.memories_created == ["new-memory-id"]


async def test_update_failure_falls_back_to_insert():
    """If the store reports the update failed, the fact must still be persisted."""
    manager = _make_manager()
    manager.store.update_memory = AsyncMock(return_value=False)
    _patch_search(
        manager,
        [{"id": "existing-id", "similarity": 0.95, "content": "near-match"}],
    )

    result = MemoryExtractionResult.empty()
    await manager._deduplicate_and_store_facts(
        facts=[_make_fact()], user_id="u1", source_chat_id="c1", result=result
    )

    manager.store.update_memory.assert_awaited_once()
    manager.store.add_memory.assert_awaited_once()
    assert result.memories_created == ["new-memory-id"]
    assert result.memories_updated == []


@pytest.mark.parametrize("threshold", [None, 0.7, 0.92])
def test_constructor_accepts_explicit_threshold(threshold):
    """Constructing via the public API should honor the dedup_threshold arg."""
    store = MagicMock()
    # Bypass EmbeddingGenerator / LLMClient construction by patching them on
    # the class for the duration of this test.
    from suzent.memory import manager as mgr_mod

    saved_emb = mgr_mod.EmbeddingGenerator
    saved_llm = mgr_mod.LLMClient
    mgr_mod.EmbeddingGenerator = lambda **kwargs: MagicMock()
    mgr_mod.LLMClient = lambda **kwargs: MagicMock()
    try:
        m = MemoryManager(store=store, dedup_threshold=threshold)
        expected = (
            threshold
            if threshold is not None
            else DEFAULT_DEDUPLICATION_SIMILARITY_THRESHOLD
        )
        assert m.dedup_threshold == expected
    finally:
        mgr_mod.EmbeddingGenerator = saved_emb
        mgr_mod.LLMClient = saved_llm
