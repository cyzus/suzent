"""Core memory carries state, not procedure.

It is injected on every turn a chat has memory enabled, so anything in it is
paid for continuously. Notebook conventions, ingest and lint runbooks, and
filing policy are procedure — they belong to the `notebook` skill, which is
loaded only when the work actually calls for it.
"""

import pytest

from suzent.memory.memory_context import format_core_memory_section

BLOCKS = {"persona": "p", "user": "u", "facts": "f", "context": "c"}


def _section(sandbox: bool = True, notebook: str | None = "/host/nb") -> str:
    return format_core_memory_section(
        BLOCKS,
        sandbox_enabled=sandbox,
        shared_path="/host/shared",
        mount_notebook=notebook,
    )


@pytest.mark.parametrize("sandbox", [True, False])
def test_core_memory_still_carries_the_blocks(sandbox: bool) -> None:
    """The state itself is the reason this section exists."""
    section = _section(sandbox)

    for value in BLOCKS.values():
        assert value in section


@pytest.mark.parametrize("sandbox", [True, False])
def test_notebook_procedure_is_not_in_the_always_on_prompt(sandbox: bool) -> None:
    section = _section(sandbox).lower()

    for procedure in (
        "index.md",
        "log.md",
        "schema.md",
        "ingest.md",
        "lint.md",
        "globtool",
        "query workflow",
        "durable output",
    ):
        assert procedure not in section, f"{procedure!r} belongs to the notebook skill"


@pytest.mark.parametrize("sandbox", [True, False])
def test_it_still_points_at_the_skill(sandbox: bool) -> None:
    """Removing the procedure must not remove the pointer to where it lives."""
    assert "`notebook` skill" in _section(sandbox)


def test_an_unconfigured_notebook_says_so_and_nothing_more() -> None:
    section = _section(sandbox=False, notebook=None)

    assert "No notebook is configured" in section
    assert "`notebook` skill" not in section


@pytest.mark.parametrize("sandbox", [True, False])
def test_the_memory_file_safety_rule_survives(sandbox: bool) -> None:
    """MEMORY.md's generated zone is overwritten by consolidation; losing that
    warning would cost the user real text."""
    section = _section(sandbox)

    assert "MEMORY.md" in section
    assert "below" in section


@pytest.mark.parametrize("sandbox", [True, False])
def test_core_memory_stays_within_budget(sandbox: bool) -> None:
    """A ceiling so procedure cannot drift back in. Was 3264 chars."""
    assert len(_section(sandbox)) < 2600, len(_section(sandbox))
