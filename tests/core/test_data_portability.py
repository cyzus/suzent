from pathlib import Path
import sqlite3
import zipfile

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


def test_export_skips_inaccessible_files(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / ".suzent"
    monkeypatch.setattr(data_portability, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_portability, "RUNTIME_DIR", data_dir / "runtime")
    monkeypatch.setattr(data_portability, "CACHE_DIR", data_dir / "cache")

    bad_file = (
        data_dir / "sandbox" / "sessions" / "one" / "node_modules" / ".bin" / "gws"
    )
    good_file = data_dir / "sandbox" / "sessions" / "one" / "notes.txt"
    bad_file.parent.mkdir(parents=True)
    good_file.write_text("keep", encoding="utf-8")
    bad_file.write_text("bad", encoding="utf-8")

    original_is_file = Path.is_file

    def fake_is_file(path: Path) -> bool:
        if path == bad_file:
            raise OSError("unreachable")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", fake_is_file)

    archive = tmp_path / "backup.zip"
    result = data_portability.export_data(archive)

    assert "sandbox/sessions/one/node_modules/.bin/gws" in result.skipped
    with zipfile.ZipFile(archive) as zf:
        assert "sandbox/sessions/one/notes.txt" in zf.namelist()
        assert "sandbox/sessions/one/node_modules/.bin/gws" not in zf.namelist()


def test_export_scrubs_api_keys_from_chats_db(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / ".suzent"
    monkeypatch.setattr(data_portability, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_portability, "RUNTIME_DIR", data_dir / "runtime")
    monkeypatch.setattr(data_portability, "CACHE_DIR", data_dir / "cache")
    data_dir.mkdir()

    db_path = data_dir / "chats.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE api_keys (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO api_keys VALUES ('OPENAI_API_KEY', 'encrypted')")
        conn.execute("CREATE TABLE notes (body TEXT)")
        conn.execute("INSERT INTO notes VALUES ('keep')")
        conn.commit()

    archive = tmp_path / "backup.zip"
    result = data_portability.export_data(archive)

    assert result.manifest["secrets"] == "excluded"
    exported_db = tmp_path / "exported.db"
    with zipfile.ZipFile(archive) as zf:
        zf.extract("chats.db", tmp_path)
    (tmp_path / "chats.db").replace(exported_db)

    with sqlite3.connect(exported_db) as conn:
        api_keys_count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        notes_count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    assert api_keys_count == 0
    assert notes_count == 1


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
