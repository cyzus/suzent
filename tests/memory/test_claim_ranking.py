"""Retrieval reads the lifecycle the dream writes.

The writer side landed in `07f24c4b`: personal claims carry `(confirmed 12x, last
YYYY-MM-DD)` and pages carry `status` / `stale_after`. Nothing read any of it — every
indexed row got a constant importance of 0.5, so a claim confirmed twelve times ranked
exactly like a one-off and a claim months past its expiry ranked exactly like one
confirmed yesterday.

`importance` is already a term in hybrid search, so it is where these signals belong.
"""

import pytest

from suzent.memory.indexer import CoreMemoryFileIndexer
from suzent.memory.markdown_store import (
    MEMORY_GENERATED_END,
    MEMORY_GENERATED_START,
    MarkdownMemoryStore,
)

BASE = 0.5
strength = CoreMemoryFileIndexer._claim_strength
lifecycle = CoreMemoryFileIndexer._parse_page_lifecycle


# --- confirmation count ---


def test_an_unconfirmed_claim_keeps_the_neutral_default():
    assert strength("- Prefers dark mode", {}) == BASE


def test_confirmations_raise_the_claim_and_saturate():
    once = strength("- Prefers dark mode", {})
    few = strength("- Prefers dark mode (confirmed 4x, last 2026-08-20)", {})
    many = strength("- Prefers dark mode (confirmed 64x, last 2026-08-20)", {})

    assert once < few < many
    assert many <= BASE + 0.25, "log-scaled: 40x and 60x must not diverge much"


def test_the_strongest_marker_on_a_chunk_wins():
    """Chunks are paragraphs, so one may hold several claims."""
    chunk = "- a (confirmed 2x, last 2026-01-01)\n- b (confirmed 30x, last 2026-08-01)"

    assert strength(chunk, {}) == strength("- b (confirmed 30x, last 2026-08-01)", {})


# --- status ---


def test_deprecated_demotes_but_never_removes():
    """A softer tombstone: still retrievable, out of the running. Deletion stays with
    tombstones so it remains reversible."""
    score = strength("- An old address (confirmed 30x)", {"status": "deprecated"})

    assert 0 < score < BASE


def test_draft_ranks_just_below_stable():
    assert strength("- A guess", {"status": "draft"}) < strength("- A guess", {})


def test_a_status_the_schema_does_not_know_is_neutral():
    """The live vault predates the schema and writes `status: active`; a page must not
    be demoted for having been written before the rule existed."""
    for status in ("active", "stable", "Active", "whatever"):
        assert strength("- Lives in Berlin", {"status": status}) == BASE


# --- stale_after ---


def test_an_expired_claim_decays_rather_than_disappearing():
    fresh = strength(
        "- Works at Acme", {"stale_after": "2027-01-01"}, today="2026-08-23"
    )
    expired = strength(
        "- Works at Acme", {"stale_after": "2026-01-01"}, today="2026-08-23"
    )

    assert expired < fresh
    assert expired > 0, "unverified is not wrong — the revisit queue decides"


def test_confirmations_still_outrank_an_expiry():
    """Something confirmed sixty times and nominally stale beats an unconfirmed
    one-off; the decay is a discount, not a veto."""
    stale_but_certain = strength(
        "- Lives in Berlin (confirmed 60x, last 2026-08-01)",
        {"stale_after": "2026-01-01"},
        today="2026-08-23",
    )

    assert stale_but_certain > 0.4


def test_a_malformed_date_is_ignored():
    assert strength("- x", {"stale_after": "soonish"}, today="2026-08-23") == BASE


# --- frontmatter parsing ---


def test_lifecycle_is_read_from_frontmatter():
    page = (
        "---\n"
        "type: personal\n"
        'status: "stable"\n'
        "stale_after: 2027-02-01\n"
        "---\n\n# Preferences\n"
    )

    assert lifecycle(page) == {"status": "stable", "stale_after": "2027-02-01"}


def test_a_page_without_frontmatter_is_still_indexable():
    assert lifecycle("# Preferences\n\n- dark mode") == {}
    assert lifecycle("---\nbroken frontmatter\n\n# Page") == {}


# --- the row build ---


@pytest.mark.asyncio
async def test_vault_pages_are_scored_and_logs_are_not(tmp_path):
    """Daily logs are raw capture with no lifecycle; only the vault carries claims."""
    indexer = CoreMemoryFileIndexer()
    captured = []

    class _Store:
        async def delete_memories_by_source_file(self, f, u):
            return True

        async def delete_memories_by_source_date(self, d, u):
            return True

        async def add_memory(self, **kw):
            captured.append((kw["content"], kw["importance"], kw["metadata"]))

    class _Emb:
        async def generate(self, text):
            return [0.1, 0.2, 0.3]

    page = (
        "---\nstatus: stable\nstale_after: 2027-01-01\n---\n\n"
        "- Prefers dark mode (confirmed 20x, last 2026-08-20)"
    )
    await indexer._reindex_file(
        "notebook", "3_Personal/prefs.md", page, _Store(), _Emb(), "u1"
    )
    scored = [c for c in captured if "dark mode" in c[0]]

    assert scored and scored[0][1] > BASE
    assert scored[0][2]["status"] == "stable"

    captured.clear()
    await indexer._reindex_file(
        "archive", "2026-08-20.md", "- [preference] dark mode", _Store(), _Emb(), "u1"
    )

    assert captured[0][1] == BASE


# --- a human edit is a different kind of evidence ---


@pytest.mark.asyncio
async def test_a_human_edit_lands_in_the_zone_generators_cannot_touch(tmp_path):
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    await store.write_memory_file("- generated claim")

    await store.write_memory_manual_zone("- Actually I moved to Berlin", "human:u1")
    await store.write_memory_file("- regenerated claim")

    text = store.memory_file_path.read_text(encoding="utf-8")

    assert "- Actually I moved to Berlin" in text
    assert "- regenerated claim" in text
    assert "- generated claim" not in text
    assert "<!-- verified: human:u1 at " in text


@pytest.mark.asyncio
async def test_a_human_edit_does_not_copy_the_generated_half_down(tmp_path):
    """The UI submits the whole file. Keeping the generated half as 'manual' would
    duplicate every fact the next pass regenerates."""
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    await store.write_memory_file("- generated claim")
    submitted = store.memory_file_path.read_text(encoding="utf-8") + "\n- my note\n"

    await store.write_memory_manual_zone(submitted, "human:u1")
    text = store.memory_file_path.read_text(encoding="utf-8")

    assert text.count("- generated claim") == 1
    assert text.count(MEMORY_GENERATED_START) == 1
    assert text.count(MEMORY_GENERATED_END) == 1
    assert "- my note" in text


@pytest.mark.asyncio
async def test_editing_facts_before_any_generation_still_works(tmp_path):
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )

    await store.write_memory_manual_zone("- first note", "human:u1")
    await store.write_memory_file("- generated")

    text = store.memory_file_path.read_text(encoding="utf-8")

    assert "- first note" in text and "- generated" in text
