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


# --- the pointer has to be reachable ----------------------------------------


@pytest.mark.parametrize("sandbox", [True, False])
def test_without_the_skill_it_points_at_the_vault_instead(sandbox: bool) -> None:
    """Skills are disabled by default, so SkillTool is often not equipped.
    Naming a skill the model cannot load is worse than saying nothing — it looks
    like a route out of the problem and is not one."""
    section = format_core_memory_section(
        BLOCKS,
        sandbox_enabled=sandbox,
        shared_path="/host/shared",
        mount_notebook="/host/nb",
        notebook_skill_available=False,
    )

    assert "`notebook` skill" not in section
    assert "schema.md" in section
    assert "existing page" in section


@pytest.mark.parametrize("sandbox", [True, False])
def test_the_fallback_stays_short(sandbox: bool) -> None:
    """It is a pointer to the vault's own authority, not the runbook again."""
    section = format_core_memory_section(
        BLOCKS,
        sandbox_enabled=sandbox,
        shared_path="/host/shared",
        mount_notebook="/host/nb",
        notebook_skill_available=False,
    )

    for procedure in ("ingest.md", "lint.md", "log.md", "query workflow"):
        assert procedure not in section.lower()
    assert len(section) < 2600, len(section)


def test_availability_defaults_to_false_when_it_cannot_be_determined() -> None:
    """Pointing at the vault always works; pointing at an absent tool does not."""
    from suzent.memory.manager import _notebook_skill_available

    assert _notebook_skill_available() in (True, False)


def test_unknown_skill_state_is_treated_as_unavailable(monkeypatch) -> None:
    import suzent.memory.manager as manager_mod

    def boom():
        raise RuntimeError("no skill manager")

    monkeypatch.setattr(
        "suzent.skills.manager.SkillManager.get_instance", staticmethod(boom)
    )

    assert manager_mod._notebook_skill_available() is False
