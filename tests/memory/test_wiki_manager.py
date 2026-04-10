from pathlib import Path


from suzent.memory.wiki_manager import WikiManager


def test_ensure_structure_creates_required_files(tmp_path: Path):
    manager = WikiManager(notebook_path=str(tmp_path))

    assert (tmp_path / "schema.md").exists()
    assert (tmp_path / "index.md").exists()
    assert (tmp_path / "log.md").exists()
    assert "# Notebook Schema" in (tmp_path / "schema.md").read_text(encoding="utf-8")
    assert "# Notebook Index" in (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "# Notebook Log" in (tmp_path / "log.md").read_text(encoding="utf-8")
    assert manager is not None


def test_ensure_structure_is_idempotent(tmp_path: Path):
    """Creating WikiManager twice on the same path must not overwrite existing files."""
    WikiManager(notebook_path=str(tmp_path))

    (tmp_path / "index.md").write_text("# Custom Index\n", encoding="utf-8")
    (tmp_path / "schema.md").write_text("# Custom Schema\n", encoding="utf-8")

    WikiManager(notebook_path=str(tmp_path))

    assert (tmp_path / "index.md").read_text(encoding="utf-8") == "# Custom Index\n"
    assert (tmp_path / "schema.md").read_text(encoding="utf-8") == "# Custom Schema\n"
