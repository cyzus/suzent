from pathlib import Path

from suzent.config import paths


def _write_skill(root: Path, name: str, body: str = "body") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} description\n---\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_legacy_user_skills_are_moved_to_flat_root(tmp_path: Path, monkeypatch) -> None:
    skills_root = tmp_path / "skills"
    legacy_root = skills_root / "user"
    legacy_skill = _write_skill(legacy_root, "custom")
    monkeypatch.setattr(paths, "SKILLS_ROOT_DIR", skills_root)
    monkeypatch.setattr(paths, "LEGACY_USER_SKILLS_DIR", legacy_root)

    paths.migrate_legacy_user_skills_dir()

    assert not legacy_skill.exists()
    assert (skills_root / "custom" / "SKILL.md").is_file()


def test_legacy_migration_preserves_name_collisions(
    tmp_path: Path, monkeypatch
) -> None:
    skills_root = tmp_path / "skills"
    legacy_root = skills_root / "user"
    legacy_skill = _write_skill(legacy_root, "custom", "legacy")
    current_skill = _write_skill(skills_root, "custom", "current")
    monkeypatch.setattr(paths, "SKILLS_ROOT_DIR", skills_root)
    monkeypatch.setattr(paths, "LEGACY_USER_SKILLS_DIR", legacy_root)

    paths.migrate_legacy_user_skills_dir()

    assert legacy_skill.is_dir()
    assert "legacy" in (legacy_skill / "SKILL.md").read_text(encoding="utf-8")
    assert "current" in (current_skill / "SKILL.md").read_text(encoding="utf-8")


def test_sync_does_not_create_managed_mirror_directories(
    tmp_path: Path, monkeypatch
) -> None:
    skills_root = tmp_path / "skills"
    legacy_root = skills_root / "user"
    skills_root.mkdir()
    monkeypatch.setattr(paths, "SKILLS_ROOT_DIR", skills_root)
    monkeypatch.setattr(paths, "LEGACY_USER_SKILLS_DIR", legacy_root)

    result = paths.sync_managed_skills_dirs()

    assert result == skills_root
    assert not (skills_root / "official").exists()
    assert not (skills_root / "external").exists()
    assert not legacy_root.exists()
