from pathlib import Path

from suzent.config import PROJECT_DIR
from suzent.skills.manager import SkillManager


def _write_skill(
    root: Path, folder: str, name: str, description: str, body: str
) -> None:
    skill_dir = root / folder
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8",
    )


def test_user_skill_overrides_builtin_by_name(tmp_path: Path):
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    _write_skill(builtin, "notebook", "notebook", "Built in", "builtin body")
    _write_skill(user, "notebook", "notebook", "User override", "user body")

    manager = SkillManager(skills_dir=builtin)
    manager.skills_dirs = [builtin, user]
    manager.loader.skills_dirs = manager.skills_dirs
    manager.persistence_file = tmp_path / "config" / "skills.json"
    manager.reload()

    skill = manager.loader.get_skill("notebook")

    assert skill is not None
    assert skill.metadata.description == "User override"
    assert skill.body == "user body"


def test_enabled_state_is_written_to_user_config_dir(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    config_dir = tmp_path / "config"
    _write_skill(skills_dir, "writer", "writer", "Writer", "body")

    manager = SkillManager(skills_dir=skills_dir)
    manager.persistence_file = config_dir / "skills.json"
    manager.enable_skill("writer")

    assert (config_dir / "skills.json").exists()
    assert "writer" in (config_dir / "skills.json").read_text(encoding="utf-8")


def test_builtin_skill_names_match_directories_and_exclude_tool_only_guides():
    manager = SkillManager(skills_dir=PROJECT_DIR / "skills")
    skills = manager.loader.list_skills()
    names = {skill.metadata.name for skill in skills}

    assert all(skill.dir.name == skill.metadata.name for skill in skills)
    assert {
        "suzent-automation",
        "suzent-canvas",
        "suzent-devices",
        "suzent-skill-creator",
        "suzent-skill-installer",
    }.issubset(names)
    assert names.isdisjoint(
        {
            "automation",
            "canvas",
            "companion-devices",
            "skill-creator",
            "skill-installer",
            "filesystem-skill",
            "browser-skill",
            "speech",
            "nodes",
        }
    )


def test_social_skill_routes_to_each_channel_reference():
    social_dir = PROJECT_DIR / "skills" / "social"
    skill_body = (social_dir / "SKILL.md").read_text(encoding="utf-8")

    for channel in ("telegram", "slack", "discord", "feishu", "wechat"):
        reference = social_dir / "references" / f"{channel}.md"

        assert f"references/{channel}.md" in skill_body
        assert reference.is_file()
