from pathlib import Path
from unittest.mock import patch

import pytest

from suzent.core.commands import CommandContext, dispatch
from suzent.core.commands.skill import skill_invocation_context
from suzent.skills.manager import SkillManager


def _write_skill(root: Path, name: str, description: str, body: str = "body") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8",
    )


@pytest.fixture
def manager(tmp_path: Path) -> SkillManager:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "writer", "Writes prose", "Use short sentences.")
    _write_skill(skills_dir, "painter", "Paints pictures")
    manager = SkillManager(skills_dir=skills_dir)
    manager.persistence_file = tmp_path / "config" / "skills.json"
    manager.enable_skill("writer")
    manager.disable_skill("painter")
    return manager


def _ctx() -> CommandContext:
    return CommandContext(chat_id="chat-1", user_id="user", surface="frontend")


def test_context_carries_the_skill_and_the_task(manager: SkillManager) -> None:
    context = skill_invocation_context(
        "/skill writer draft a note, don't be long", manager
    )

    assert context is not None
    skill_id = manager.loader.get_skill("writer").id
    assert f'<skill name="writer" id="{skill_id}">' in context
    assert "Use short sentences." in context
    assert "do not load it again with skill_execute" in context
    assert "Carry out the rest of their message" in context


def test_context_without_a_task_asks_what_to_do(manager: SkillManager) -> None:
    context = skill_invocation_context("/skills writer", manager)

    assert context is not None
    assert "ask what they want done" in context


def test_context_is_not_truncated(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    long_body = "step\n" * 3000
    _write_skill(skills_dir, "long", "A long skill", long_body + "THE END")
    manager = SkillManager(skills_dir=skills_dir)
    manager.persistence_file = tmp_path / "config" / "skills.json"
    manager.enable_skill("long")

    context = skill_invocation_context("/skill long go", manager)

    assert context is not None
    assert "THE END" in context


@pytest.mark.parametrize(
    "message",
    ["/skill", "/skill painter go", "/skill missing go", "hello", "/skillful x"],
)
def test_no_context_unless_an_enabled_skill_is_named(
    manager: SkillManager, message: str
) -> None:
    assert skill_invocation_context(message, manager) is None


@pytest.mark.asyncio
async def test_bare_command_lists_enabled_skills(manager: SkillManager) -> None:
    with patch(
        "suzent.skills.manager.get_skill_manager_for_chat", return_value=manager
    ):
        response = await dispatch(_ctx(), "/skill")

    assert "`writer` — Writes prose" in response
    assert "painter" not in response


@pytest.mark.asyncio
async def test_command_explains_unusable_skills(manager: SkillManager) -> None:
    with patch(
        "suzent.skills.manager.get_skill_manager_for_chat", return_value=manager
    ):
        disabled = await dispatch(_ctx(), "/skill painter")
        missing = await dispatch(_ctx(), "/skill missing")

    assert "turned off" in disabled
    assert "No skill named `missing`" in missing


def test_context_keeps_the_requested_source(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _write_skill(first, "writer", "First writer", "first body")
    _write_skill(second, "writer", "Second writer", "second body")
    manager = SkillManager(skills_dir=first)
    manager.skills_dirs = [first, second]
    manager.loader.skills_dirs = manager.skills_dirs
    manager.loader.source_ids[second.resolve()] = "repo"
    manager.persistence_file = tmp_path / "config" / "skills.json"
    manager.reload()
    ids = [s.id for s in manager.loader.list_skills()]
    assert len(set(ids)) == 2
    requested = next(
        i
        for i in ids
        if manager.loader.get_skill(i).metadata.description == "First writer"
    )
    manager.enable_skill(requested)

    context = skill_invocation_context(f"/skill {requested} go", manager)

    assert context is not None
    assert f'id="{requested}"' in context
    assert "first body" in context
    assert "second body" not in context
