from pathlib import Path

from suzent.core import data_portability


def test_export_excludes_runtime_cache_and_exports(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / ".suzent"
    monkeypatch.setattr(data_portability, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_portability, "RUNTIME_DIR", data_dir / "runtime")
    monkeypatch.setattr(data_portability, "CACHE_DIR", data_dir / "cache")

    (data_dir / "runtime").mkdir(parents=True)
    (data_dir / "cache").mkdir()
    (data_dir / "exports").mkdir()
    (data_dir / "skills" / "writer").mkdir(parents=True)
    (data_dir / "skills" / "writer" / "SKILL.md").write_text("skill", encoding="utf-8")
    (data_dir / "chats.db").write_text("db", encoding="utf-8")
    (data_dir / ".secret_key").write_text("secret", encoding="utf-8")

    result = data_portability.export_data(tmp_path / "backup.zip")

    assert "chats.db" in result.included
    assert "skills" in result.included
    assert "runtime" not in result.included
    assert "cache" not in result.included
    assert "exports" not in result.included
    assert ".secret_key" not in result.included


def test_import_dry_run_does_not_replace_data(monkeypatch, tmp_path: Path):
    source_dir = tmp_path / "source"
    data_dir = tmp_path / ".suzent"
    monkeypatch.setattr(data_portability, "DATA_DIR", source_dir)
    monkeypatch.setattr(data_portability, "RUNTIME_DIR", source_dir / "runtime")
    monkeypatch.setattr(data_portability, "CACHE_DIR", source_dir / "cache")
    source_dir.mkdir()
    (source_dir / "chats.db").write_text("incoming", encoding="utf-8")
    archive = tmp_path / "backup.zip"
    data_portability.export_data(archive)

    monkeypatch.setattr(data_portability, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_portability, "RUNTIME_DIR", data_dir / "runtime")
    monkeypatch.setattr(data_portability, "CACHE_DIR", data_dir / "cache")
    data_dir.mkdir()
    (data_dir / "chats.db").write_text("current", encoding="utf-8")

    result = data_portability.import_data(archive, dry_run=True)

    assert result.valid is True
    assert (data_dir / "chats.db").read_text(encoding="utf-8") == "current"
