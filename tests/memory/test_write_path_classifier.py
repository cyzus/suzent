"""The write path may recognise a re-statement, and nothing more.

Issue #34 was write-time deduplication swallowing an update. The classifier is allowed
to divert one specific case — the same claim, in the same words, already durably
recorded, adding no new specifics — into the confirmations sidecar. Every test here
exists to hold that line: anything that could be an update is written exactly as it
was before this landed.
"""

import pytest

from suzent.memory.classifier import (
    CONFIRM_SIMILARITY,
    ClaimVerdict,
    claim_similarity,
    classify_fact,
    new_specifics,
    polarity_differs,
)
from suzent.memory.markdown_store import MarkdownMemoryStore
from suzent.memory.models import ExtractedFact

KNOWN = ["User prefers dark mode in the editor"]


def _fact(content: str, **kw) -> ExtractedFact:
    return ExtractedFact(content=content, category="preference", importance=0.5, **kw)


# --- similarity ---


def test_the_same_claim_reworded_scores_high_and_a_different_one_does_not():
    same = claim_similarity(
        "User prefers dark mode in the editor",
        "the user prefers dark mode in an editor",
    )
    different = claim_similarity(
        "User prefers dark mode in the editor", "User works at a hardware startup"
    )

    assert same > 0.97
    assert different < 0.3


def test_similarity_ignores_the_daily_log_prefix():
    assert claim_similarity("- [preference] likes tea", "likes tea") == 1.0


# --- the guard against folding in an update ---


def test_a_new_specific_is_what_separates_an_update_from_a_repeat():
    assert new_specifics("moved to Berlin in 2024", "moved to Berlin") == ["2024"]
    assert new_specifics("moved to Berlin", "moved to Berlin in 2024") == []


@pytest.mark.parametrize(
    "content",
    [
        "User prefers dark mode in the editor since 2025-01-01",
        'User prefers dark mode in the editor, theme "Nord"',
        "User prefers dark mode in the editor at 90% brightness",
    ],
)
def test_added_detail_is_a_revision_even_when_the_prose_is_identical(content):
    verdict = classify_fact(content, KNOWN)

    assert verdict.is_revision
    assert not verdict.is_confirmation
    assert verdict.new_specifics


def test_a_contradiction_is_never_a_confirmation():
    verdict = classify_fact("User prefers light mode in the editor", KNOWN)

    assert not verdict.is_confirmation


def test_an_unrelated_fact_is_new():
    assert classify_fact("User is learning Portuguese", KNOWN).kind == "new"


def test_a_re_statement_is_a_confirmation():
    verdict = classify_fact("The user prefers dark mode in the editor", KNOWN)

    assert verdict.is_confirmation
    assert verdict.matched == KNOWN[0]


def test_nothing_known_means_nothing_is_diverted():
    assert classify_fact("User prefers dark mode", []).kind == "new"
    assert classify_fact("User prefers dark mode", None).kind == "new"


# --- the sidecar ---


@pytest.mark.asyncio
async def test_confirmations_group_by_claim_and_keep_the_last_date(tmp_path):
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )

    await store.append_confirmation("likes tea", "likes tea", "2026-08-01")
    await store.append_confirmation("Likes  tea", "likes tea", "2026-08-09")
    await store.append_confirmation("uses vim", "uses vim", "2026-08-05")

    rows = store.summarize_confirmations()

    assert rows[0]["count"] == 2 and rows[0]["last"] == "2026-08-09"
    assert [r["count"] for r in rows] == [2, 1]


@pytest.mark.asyncio
async def test_clearing_keeps_what_arrived_during_the_run(tmp_path):
    """The dream takes minutes and conversations keep confirming things while it runs.
    Truncating the file wholesale would drop exactly the records it exists to keep."""
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    await store.append_confirmation("seen by the dream", "x", "2026-08-01")
    consumed = len(store.read_confirmations())
    await store.append_confirmation("arrived mid-run", "y", "2026-08-01")

    store.clear_confirmations(consumed)
    remaining = store.read_confirmations()

    assert [r["content"] for r in remaining] == ["arrived mid-run"]


@pytest.mark.asyncio
async def test_a_malformed_line_does_not_break_the_sidecar(tmp_path):
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    store.confirmations_path.write_text("{not json\n", encoding="utf-8")
    await store.append_confirmation("likes tea", "likes tea", "2026-08-01")

    assert [r["content"] for r in store.read_confirmations()] == ["likes tea"]


# --- the split, as the write path performs it ---


class _Store(MarkdownMemoryStore):
    pass


@pytest.fixture
def manager(tmp_path):
    from suzent.memory.manager import MemoryManager

    mgr = MemoryManager.__new__(MemoryManager)
    mgr.markdown_store = _Store(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    return mgr


@pytest.mark.asyncio
async def test_only_durable_matches_may_divert_a_write(manager):
    """A transcript row is the user having said something, not memory holding it. If a
    repeat matched only there and we skipped the log write, the claim would exist
    nowhere durable at all."""
    facts = [_fact("The user prefers dark mode in the editor")]
    transcript_only = [{"content": KNOWN[0], "durable": False}]

    to_write, confirmed = await manager._split_confirmations(
        facts, transcript_only, "c1"
    )

    assert len(to_write) == 1 and not confirmed


@pytest.mark.asyncio
async def test_a_confirmation_leaves_the_log_and_lands_in_the_sidecar(manager):
    facts = [
        _fact("The user prefers dark mode in the editor"),
        _fact("User is learning Portuguese"),
    ]
    known = [{"content": KNOWN[0], "durable": True}]

    to_write, confirmed = await manager._split_confirmations(facts, known, "c1")

    assert [f.content for f in to_write] == ["User is learning Portuguese"]
    assert confirmed == [("The user prefers dark mode in the editor", KNOWN[0])]
    assert manager.markdown_store.read_confirmations()[0]["matched"] == KNOWN[0]


@pytest.mark.asyncio
async def test_a_revision_is_still_written_and_is_tagged(manager):
    facts = [_fact("User prefers dark mode in the editor since 2025-01-01")]
    known = [{"content": KNOWN[0], "durable": True}]

    to_write, confirmed = await manager._split_confirmations(facts, known, "c1")

    assert len(to_write) == 1 and not confirmed
    assert "revision" in to_write[0].tags


@pytest.mark.asyncio
async def test_a_failed_sidecar_write_falls_back_to_the_log(manager, monkeypatch):
    async def _boom(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(manager.markdown_store, "append_confirmation", _boom)
    facts = [_fact("The user prefers dark mode in the editor")]
    known = [{"content": KNOWN[0], "durable": True}]

    to_write, confirmed = await manager._split_confirmations(facts, known, "c1")

    assert len(to_write) == 1 and not confirmed


@pytest.mark.asyncio
async def test_with_nothing_recalled_the_path_is_untouched(manager):
    facts = [_fact("anything at all")]

    to_write, confirmed = await manager._split_confirmations(facts, [], "c1")

    assert to_write == facts and not confirmed


def test_verdict_kinds_are_mutually_exclusive():
    assert not ClaimVerdict(kind="new").is_confirmation
    assert not ClaimVerdict(kind="new").is_revision


# --- negation ---


@pytest.mark.parametrize(
    "correction",
    [
        "The user does not prefer dark mode in the editor",
        "The user no longer prefers dark mode in the editor",
        "The user doesn't prefer dark mode in the editor",
    ],
)
def test_a_negated_restatement_is_never_a_confirmation(correction):
    """Negation is the one word that reverses a claim instead of decorating it.

    Step 4 of the dream prompt tells the agent a contradicting restatement never
    reaches the confirmations list, and bumps the marker without re-reading the page.
    If a correction were folded in as a confirmation, the write path would swallow an
    update and the dream would count it as evidence *for* the claim it contradicts —
    issue #34 all over again, with a false confirmation on top.
    """
    verdict = classify_fact(correction, KNOWN)

    assert not verdict.is_confirmation


def test_negation_survives_a_sentence_long_enough_to_dilute_it():
    """The failure mode a lexical score alone cannot catch: on a long claim a single
    "not" moves Dice by ~0.03, which lands inside the confirmation band."""
    claim = (
        "The nightly deployment pipeline is available on the staging cluster, "
        "publishes a coverage report to the shared engineering channel each morning, "
        "and mirrors its artifacts to the backup registry in Frankfurt"
    )
    negated = claim.replace("is available", "is not available")

    assert claim_similarity(claim, negated) >= CONFIRM_SIMILARITY
    assert polarity_differs(claim, negated)
    assert not classify_fact(negated, [claim]).is_confirmation


def test_matching_negations_still_confirm():
    """Only a *difference* in polarity is claim-bearing. Two statements that are both
    negative say the same thing, and must stay eligible for the sidecar."""
    known = ["The user does not want email notifications"]

    assert classify_fact(
        "The user does not want email notifications", known
    ).is_confirmation


def test_spelling_a_contraction_out_is_not_a_difference():
    assert not polarity_differs(
        "the build isn't reproducible", "the build isnt reproducible"
    )


@pytest.mark.asyncio
async def test_clearing_keeps_claims_the_prompt_could_not_fit(tmp_path):
    """`summarize_confirmations` is bounded; the file is not.

    A busy stretch can leave more distinct claims pending than the prompt shows. The
    agent bumps markers only for what it saw, so dropping by position alone would
    destroy the evidence for the rest — and the sidecar is the *only* record that
    those facts recurred, because the write path deliberately kept them out of the
    daily log.
    """
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    await store.append_confirmation("shown to the agent", "x", "2026-08-01")
    await store.append_confirmation("did not fit in the prompt", "y", "2026-08-01")
    consumed = len(store.read_confirmations())

    store.clear_confirmations(consumed, folded=["shown to the agent"])

    assert [r["content"] for r in store.read_confirmations()] == [
        "did not fit in the prompt"
    ]


@pytest.mark.asyncio
async def test_a_folded_claim_is_cleared_however_its_repeats_are_interleaved(tmp_path):
    store = MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )
    await store.append_confirmation("Prefers dark mode", "x", "2026-08-01")
    await store.append_confirmation("unshown", "y", "2026-08-01")
    await store.append_confirmation("prefers   DARK mode", "x", "2026-08-02")
    consumed = len(store.read_confirmations())

    store.clear_confirmations(consumed, folded=["Prefers dark mode"])

    assert [r["content"] for r in store.read_confirmations()] == ["unshown"]
