"""Regression tests for dream consolidation prompt invariants."""

from suzent.memory import memory_context


def test_dream_conflict_instructions_do_not_write_log_md():
    """Conflict handling must happen on content pages, not the runner-owned log."""
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
    assert "Put conflicts on content pages" in instructions
    assert "schema's appropriate location" in instructions
