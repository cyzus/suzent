"""Personal claims must carry lifecycle, not just accumulate.

A fact the user repeats is one claim confirmed many times. Without somewhere to put
that count the dream can only retire the repeat, losing the strongest ranking signal
in the corpus; without `stale_after` nothing ever revisits a claim that went out of
date. Both rules live in the dream prompt as well as the schema, because schema.md is
seeded once per vault and existing vaults predate them.
"""

from suzent.memory import memory_context

SCHEMA = "skills/notebook/schema_example.md"
OKF = "skills/notebook/okf.md"


def _dream_text() -> str:
    return memory_context.build_dream_instructions(
        memory_context.resolve_dream_roots(sandbox_enabled=True),
        start="2026-01-01",
        end="2026-01-02",
        confirmations="   (none pending)",
        revisits="   (none due)",
    )


def _lint_text() -> str:
    return memory_context.build_lint_instructions(
        memory_context.resolve_dream_roots(sandbox_enabled=True)
    )


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_duplicates_are_confirmed_not_restated():
    text = _dream_text()

    assert "confirmed 12x, last YYYY-MM-DD" in text
    assert "Never add a second" in text


def test_a_contradicting_repeat_is_not_a_confirmation():
    """Otherwise a reversal would be counted as evidence for the thing it reverses."""
    assert "CONTRADICTS" in _dream_text()


def test_lifecycle_rules_do_not_depend_on_the_seeded_schema():
    text = _dream_text()

    assert "whether or not this vault's" in text
    assert "stale_after" in text


def test_lint_never_deletes_or_unconfirms_a_stale_personal_claim():
    text = _lint_text()

    assert "never delete it" in text
    assert "never reset a claim's confirmation marker" in text


def test_schema_documents_the_personal_page_contract():
    schema = _read(SCHEMA)

    assert "type: personal" in schema
    assert "confirmed 12x" in schema
    for category in ("preference", "technical", "goal", "context"):
        assert category in schema


def test_okf_profile_maps_the_marker_to_usage_count():
    okf = _read(OKF)

    assert "usage_count" in okf
    assert "stale_after" in okf
