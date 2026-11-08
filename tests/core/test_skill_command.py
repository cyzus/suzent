from pathlib import Path
from unittest.mock import patch

import pytest

from suzent.core.commands import CommandContext, dispatch
from suzent.core.commands.skill import skill_invocation_reminder
from suzent.skills.manager import SkillManager


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nbody\n",
        encoding="utf-8",
    )


@pytest.fixture
def manager(tmp_path: Path) -> SkillManager:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "writer", "Writes prose")
    _write_skill(skills_dir, "painter", "Paints pictures")
    manager = SkillManager(skills_dir=skills_dir)
    manager.persistence_file = tmp_path / "config" / "skills.json"
    manager.enable_skill("writer")
    manager.disable_skill("painter")
    return manager


def _ctx() -> CommandContext:
    return CommandContext(chat_id="chat-1", user_id="user", surface="frontend")


def test_reminder_names_the_skill_and_the_task(manager: SkillManager) -> None:
    reminder = skill_invocation_reminder(
        "/skill writer draft a note, don't be long", manager
    )

    assert reminder is not None
    assert 'skill_name="writer"' in reminder
    assert "carry out the rest of their message" in reminder


def test_reminder_without_a_task_asks_what_to_do(manager: SkillManager) -> None:
    reminder = skill_invocation_reminder("/skills writer", manager)

    assert reminder is not None
    assert "ask what they want done" in reminder


@pytest.mark.parametrize(
    "message",
    ["/skill", "/skill painter go", "/skill missing go", "hello", "/skillful x"],
)
def test_no_reminder_unless_an_enabled_skill_is_named(
    manager: SkillManager, message: str
) -> None:
    assert skill_invocation_reminder(message, manager) is None


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
