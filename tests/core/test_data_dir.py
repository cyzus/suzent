from pathlib import Path

from suzent.config import _migrate_legacy_data_dir, get_data_dir


def test_get_data_dir_defaults_to_home_suzent(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("SUZENT_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert get_data_dir() == (tmp_path / ".suzent").resolve()


def test_get_data_dir_honors_override(monkeypatch, tmp_path: Path):
    custom = tmp_path / "custom-data"
    monkeypatch.setenv("SUZENT_DATA_DIR", str(custom))

    assert get_data_dir() == custom.resolve()


def test_migrate_legacy_data_dir_copies_when_destination_empty(tmp_path: Path):
    project_dir = tmp_path / "repo"
    legacy_dir = project_dir / ".suzent"
    data_dir = tmp_path / "home" / ".suzent"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "chats.db").write_text("legacy", encoding="utf-8")

    _migrate_legacy_data_dir(project_dir, data_dir)

    assert (data_dir / "chats.db").read_text(encoding="utf-8") == "legacy"
    assert (legacy_dir / "MIGRATED.md").exists()


def test_migrate_legacy_data_dir_does_not_overwrite_existing_data(tmp_path: Path):
    project_dir = tmp_path / "repo"
    legacy_dir = project_dir / ".suzent"
    data_dir = tmp_path / "home" / ".suzent"
    legacy_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    (legacy_dir / "chats.db").write_text("legacy", encoding="utf-8")
    (data_dir / "chats.db").write_text("existing", encoding="utf-8")

    _migrate_legacy_data_dir(project_dir, data_dir)

    assert (data_dir / "chats.db").read_text(encoding="utf-8") == "existing"
