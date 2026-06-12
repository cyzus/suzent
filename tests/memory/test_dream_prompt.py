"""Regression tests for dream consolidation prompt invariants."""

from suzent.memory import memory_context


def test_dream_conflict_instructions_do_not_write_log_md():
    """Conflict handling must happen on content pages, not the runner-owned log."""
    instructions = (
        memory_context.DREAM_SYSTEM_PROMPT + "\n" + memory_context.DREAM_INSTRUCTIONS
    )

    assert "prepend `[!alert]" not in instructions
    assert "Put conflicts on content pages" in instructions
    assert "schema's appropriate location" in instructions
