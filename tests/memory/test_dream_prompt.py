"""Regression tests for dream consolidation prompt invariants."""

from suzent.memory import memory_context


def test_dream_conflict_instructions_do_not_write_log_md():
    """An unsettled conflict becomes a question for the user, not a log.md entry."""
    roots = memory_context.resolve_dream_roots(sandbox_enabled=True)
    instructions = (
        memory_context.build_dream_system_prompt(roots)
        + "\n"
        + memory_context.build_dream_instructions(
            roots,
            start="2026-01-01",
            end="2026-01-02",
            confirmations="   (none pending)",
            revisits="   (none due)",
        )
    )

    assert "prepend `[!alert]" not in instructions
    assert "Put conflicts in the review queue, never in log.md" in instructions
    assert ".state/review_queue.md" in instructions
    assert "Do NOT write to log.md" in instructions
