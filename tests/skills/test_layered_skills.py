from pathlib import Path

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
