"""MEMORY.md has three writers and used to have no merge.

Two generators (`refresh_core_memory_facts`, `promote_memory_md`) rewrite it, and the
agent edits it directly because the core-memory prompt tells it to. `write_memory_file`
was an unconditional `write_text`, so a note the agent added was destroyed by whichever
generator fired next — typically within minutes, silently.

The fix is a marked generated zone: generators own the region between the markers,
everything after the end marker is copied through untouched.
"""

import pytest

from suzent.memory import memory_context
from suzent.memory.markdown_store import (
    MEMORY_GENERATED_END,
    MEMORY_GENERATED_START,
    MarkdownMemoryStore,
)


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )


# --- the generated zone ---


@pytest.mark.asyncio
async def test_first_write_creates_a_marked_file(store):
    await store.write_memory_file("- Prefers dark mode")

    text = store.memory_file_path.read_text(encoding="utf-8")

    assert text.startswith("# Long-term Memory")
    assert MEMORY_GENERATED_START in text
    assert MEMORY_GENERATED_END in text
    assert "- Prefers dark mode" in text


@pytest.mark.asyncio
async def test_regeneration_replaces_only_the_generated_zone(store):
    await store.write_memory_file("- Old summary")
    marked = store.memory_file_path.read_text(encoding="utf-8")
    store.memory_file_path.write_text(
        marked + "\n## Pinned\n- Never call me Bob\n", encoding="utf-8"
    )

    await store.write_memory_file("- New summary")
    text = store.memory_file_path.read_text(encoding="utf-8")

    assert "- New summary" in text
    assert "- Old summary" not in text
    assert "- Never call me Bob" in text


@pytest.mark.asyncio
async def test_manual_zone_survives_many_regenerations(store):
    await store.write_memory_file("- Gen 0")
    store.memory_file_path.write_text(
        store.memory_file_path.read_text(encoding="utf-8") + "\n- pinned note\n",
        encoding="utf-8",
    )

    for i in range(1, 5):
        await store.write_memory_file(f"- Gen {i}")

    text = store.memory_file_path.read_text(encoding="utf-8")

    assert text.count("- pinned note") == 1, "the manual zone must not accumulate"
    assert "- Gen 4" in text and "- Gen 3" not in text


# --- files that predate the markers ---


@pytest.mark.asyncio
async def test_a_file_we_wrote_before_markers_is_replaced_wholesale(store):
    """The old footer is the signature: that content is ours, not the user's."""
    store.memory_file_path.write_text(
        "# Long-term Memory\n\n- stale generated line\n\n---\n"
        "*Last updated: 2026-01-01 09:00 UTC*\n",
        encoding="utf-8",
    )

    await store.write_memory_file("- fresh")
    text = store.memory_file_path.read_text(encoding="utf-8")

    assert "- stale generated line" not in text
    assert "- fresh" in text


@pytest.mark.asyncio
async def test_an_unrecognised_file_is_treated_as_entirely_manual(store):
    """Degrade safe: if we cannot prove we wrote it, we do not throw it away."""
    store.memory_file_path.write_text(
        "# My notes\n\n- the user typed this by hand\n", encoding="utf-8"
    )

    await store.write_memory_file("- generated")
    text = store.memory_file_path.read_text(encoding="utf-8")

    assert "- the user typed this by hand" in text
    assert "- generated" in text
    assert text.index("- generated") < text.index("- the user typed this by hand")


def test_manual_tail_is_pure(store):
    assert store.manual_tail("") == ""
    assert store.manual_tail("   \n ") == ""
    assert store.manual_tail(f"a\n{MEMORY_GENERATED_END}\n\nb\n") == "b"


# --- one timestamp, not two ---


@pytest.mark.asyncio
async def test_exactly_one_timestamp_and_it_is_utc(store):
    """`refresh_core_memory_facts` stamped a naive local time into the content while
    the store stamped UTC, so every generated file carried two timestamps an hour
    apart in BST."""
    await store.write_memory_file("- a fact")
    text = store.memory_file_path.read_text(encoding="utf-8")

    assert text.count("Consolidated") == 1
    assert "UTC" in text
    assert "Last updated" not in text


# --- the agent has to be told ---


def test_prompt_points_the_agent_below_the_marker():
    prompt = memory_context.format_core_memory_section({}, sandbox_enabled=True)

    assert MEMORY_GENERATED_END in prompt
    assert "below" in prompt


# --- which generator owns the file ---


class _StubStore:
    async def list_memories(self, **kwargs):
        return [{"content": "an indexed fact", "importance": 0.5}]


class _StubLLM:
    def __init__(self):
        self.calls = 0

    async def complete(self, **kwargs):
        self.calls += 1
        return "- summarised"


def _manager(tmp_path):
    from suzent.memory.manager import MemoryManager

    mgr = MemoryManager.__new__(MemoryManager)
    mgr.store = _StubStore()
    mgr.llm_client = _StubLLM()
    mgr.markdown_store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    return mgr


@pytest.mark.asyncio
async def test_legacy_refresh_no_longer_filters_on_a_dead_column(tmp_path):
    """The indexer stamps every row 0.5, so a >=0.7 gate matched only pre-June legacy
    rows: MEMORY.md was being rebuilt from months-old data and would have gone empty
    the moment those rows were retired."""
    mgr = _manager(tmp_path)

    async def _stats(user_id):
        return {"total_memories": 1}

    mgr.get_memory_stats = _stats

    await mgr.refresh_core_memory_facts("user-1")

    assert mgr.llm_client.calls == 1
    assert "- summarised" in mgr.markdown_store.memory_file_path.read_text("utf-8")


@pytest.mark.asyncio
async def test_legacy_refresh_stands_down_once_the_vault_has_pages(tmp_path):
    """Two writers, one file: the better-informed one wins as soon as it can run."""
    mgr = _manager(tmp_path)
    personal = mgr.markdown_store.notebook_dir / "3_Personal"
    personal.mkdir(parents=True, exist_ok=True)
    (personal / "identity.md").write_text("- consolidated", encoding="utf-8")

    await mgr.refresh_core_memory_facts("user-1")

    assert mgr.llm_client.calls == 0
    assert not mgr.markdown_store.memory_file_path.exists()
