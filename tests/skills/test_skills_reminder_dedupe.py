"""The skill catalog is advertised once per distinct catalog, not once per wording.

Deduplication used to match the rendered lines against history, which failed in
both directions: rewording a description re-sent the whole catalog as if it were
new, and a line that differed cosmetically was re-sent every turn forever.
"""

from types import SimpleNamespace
from typing import Any, Optional

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart

from suzent.skills.hooks import (
    CATALOG_HEADER,
    CATALOG_MARKER_PREFIX,
    catalog_revision,
    latest_advertised_revision,
    skills_reminder_hook,
)


def _skill(
    skill_id: str,
    description: str = "does a thing",
    name: Optional[str] = None,
    virtual_path: Optional[str] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=skill_id,
        metadata=SimpleNamespace(name=name or skill_id, description=description),
        virtual_path=virtual_path or f"/skills/{skill_id}",
        path=SimpleNamespace(resolve=lambda: f"/host/skills/{skill_id}"),
    )


class _Manager:
    def __init__(self, skills: list[Any], enabled: Optional[set[str]] = None) -> None:
        self._skills = skills
        self._enabled = enabled if enabled is not None else {s.id for s in skills}
        self.loader = SimpleNamespace(list_skills=lambda: list(self._skills))

    def has_enabled_skills(self) -> bool:
        return bool(self._enabled)

    def is_skill_enabled(self, skill_id: str) -> bool:
        return skill_id in self._enabled


def _deps(
    manager: _Manager, history_text: str = "", sandbox_enabled: bool = True
) -> SimpleNamespace:
    messages = (
        [ModelRequest(parts=[UserPromptPart(content=history_text)])]
        if history_text
        else []
    )
    return SimpleNamespace(
        skill_manager=manager, sandbox_enabled=sandbox_enabled, last_messages=messages
    )


async def _run(
    manager: _Manager, history_text: str = "", sandbox_enabled: bool = True
) -> Optional[str]:
    return await skills_reminder_hook(
        "chat-1", _deps(manager, history_text, sandbox_enabled)
    )


def _advertised(revision: str) -> str:
    """History as this hook writes it, header included."""
    return f"{CATALOG_HEADER}\n[{CATALOG_MARKER_PREFIX}{revision}]\n\n- x: y"


# --- first advertisement ----------------------------------------------------


@pytest.mark.asyncio
async def test_advertises_the_catalog_with_a_revision_marker() -> None:
    out = await _run(_Manager([_skill("docx"), _skill("pdf")]))

    assert out is not None
    assert CATALOG_MARKER_PREFIX in out
    assert "docx" in out and "pdf" in out


@pytest.mark.asyncio
async def test_says_nothing_when_no_skills_are_enabled() -> None:
    assert await _run(_Manager([_skill("docx")], enabled=set())) is None
    assert (
        await skills_reminder_hook("chat-1", SimpleNamespace(skill_manager=None))
        is None
    )


@pytest.mark.asyncio
async def test_disabled_skills_are_not_advertised() -> None:
    out = await _run(_Manager([_skill("docx"), _skill("pdf")], enabled={"docx"}))

    assert out is not None
    assert "docx" in out
    assert "pdf" not in out


# --- deduplication ----------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unchanged_catalog_is_not_repeated() -> None:
    manager = _Manager([_skill("docx")])
    first = await _run(manager)

    assert first is not None
    assert await _run(manager, history_text=first) is None


@pytest.mark.asyncio
async def test_adding_a_skill_re_advertises() -> None:
    first = await _run(_Manager([_skill("docx")]))

    assert first is not None
    grown = _Manager([_skill("docx"), _skill("pdf")])
    assert await _run(grown, history_text=first) is not None


@pytest.mark.asyncio
async def test_rewording_a_description_re_advertises() -> None:
    """The model routes on descriptions, so a changed one is new information."""
    first = await _run(_Manager([_skill("docx", description="old wording")]))
    out = await _run(
        _Manager([_skill("docx", description="new wording")]), history_text=first or ""
    )

    assert out is not None and "new wording" in out


@pytest.mark.asyncio
async def test_catalog_order_does_not_cause_a_repeat() -> None:
    """Ordering is an implementation detail of the loader, not a change."""
    first = await _run(_Manager([_skill("docx"), _skill("pdf")]))
    reordered = _Manager([_skill("pdf"), _skill("docx")])

    assert await _run(reordered, history_text=first or "") is None


@pytest.mark.asyncio
async def test_switching_to_host_paths_re_advertises() -> None:
    """Locations change with the sandbox flag, so the advice really is stale."""
    first = await _run(_Manager([_skill("docx")]), sandbox_enabled=True)
    out = await _run(
        _Manager([_skill("docx")]), history_text=first or "", sandbox_enabled=False
    )

    assert out is not None
    assert "/host/skills/docx" in out


@pytest.mark.asyncio
async def test_a_changed_location_re_advertises() -> None:
    """Same id and description, different path — the model was told the old one."""
    first = await _run(_Manager([_skill("docx", virtual_path="/skills/docx")]))
    out = await _run(
        _Manager([_skill("docx", virtual_path="/skills/moved/docx")]),
        history_text=first or "",
    )

    assert out is not None
    assert "/skills/moved/docx" in out


@pytest.mark.asyncio
async def test_an_unrelated_history_does_not_suppress_the_catalog() -> None:
    assert (
        await _run(_Manager([_skill("docx")]), history_text="read the docx") is not None
    )


@pytest.mark.asyncio
async def test_a_dropped_marker_re_advertises() -> None:
    """Compaction removes old turns and restart drops reminder blocks. The marker
    travels with the message, so it disappears exactly when the catalog does and
    the agent is told again — a durable 'already told' store would not."""
    manager = _Manager([_skill("docx")])
    first = await _run(manager)
    assert await _run(manager, history_text=first or "") is None

    assert (
        await _run(manager, history_text="...summary of earlier turns...") is not None
    )


@pytest.mark.asyncio
async def test_a_catalog_that_changes_back_is_re_advertised() -> None:
    """A→B→A must not stay silent: history still holds A's marker, but what the
    model was most recently told is B."""
    only_docx = _Manager([_skill("docx")])
    both = _Manager([_skill("docx"), _skill("pdf")])

    first = await _run(only_docx)
    second = await _run(both, history_text=first or "")
    assert second is not None

    back = await _run(only_docx, history_text=f"{first}\n{second}")

    assert back is not None, "the model's current view is B, so A is new again"


# --- which marker counts ----------------------------------------------------


def test_the_latest_marker_is_the_one_that_counts() -> None:
    history = (
        f"{_advertised('aaaaaaaaaaaa')}\n...later...\n{_advertised('bbbbbbbbbbbb')}"
    )

    assert latest_advertised_revision(history) == "bbbbbbbbbbbb"


def test_no_marker_means_never_advertised() -> None:
    assert latest_advertised_revision("") is None
    assert latest_advertised_revision("nothing relevant here") is None


def test_marker_shaped_text_without_our_header_is_ignored() -> None:
    """A bare marker matches text this hook never wrote — a repository reminder,
    a goal, something a user pasted — and since the newest match wins, that text
    would decide whether the catalog is advertised."""
    assert latest_advertised_revision("[skills-catalog rev=aaaaaaaaaaaa]") is None


@pytest.mark.asyncio
async def test_pasted_marker_text_cannot_suppress_the_catalog() -> None:
    manager = _Manager([_skill("docx")])
    genuine = await _run(manager)
    assert genuine is not None
    revision = latest_advertised_revision(genuine)
    assert revision is not None

    pasted = f"see [{CATALOG_MARKER_PREFIX}{revision}] in the logs"

    assert await _run(manager, history_text=pasted) is not None


# --- the revision itself ----------------------------------------------------


def test_revision_is_order_independent() -> None:
    """Loader ordering is an implementation detail, not a catalog change."""
    assert catalog_revision(["- docx: d", "- pdf: p"]) == catalog_revision(
        ["- pdf: p", "- docx: d"]
    )


@pytest.mark.parametrize(
    "lines",
    [
        pytest.param(["- docx: changed"], id="description"),
        pytest.param(["- docx: d", "- pdf: p"], id="added-skill"),
        pytest.param(["- docx: d (Location: /elsewhere)"], id="location"),
    ],
)
def test_revision_changes_with_anything_that_would_be_emitted(
    lines: list[str],
) -> None:
    """Hashing the rendered lines means nothing emitted can slip past it."""
    assert catalog_revision(lines) != catalog_revision(["- docx: d"])
