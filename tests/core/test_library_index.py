from pathlib import Path

from suzent.core.library_index import add_to_file_index, unindexed_artifacts


def test_creates_file_index_section(tmp_path: Path) -> None:
    (tmp_path / "context.md").write_text("## Overview\n\nA project.\n")
    added = add_to_file_index(
        tmp_path, [(tmp_path / "artifacts/images/a.png", "generated image")]
    )
    text = (tmp_path / "context.md").read_text()
    assert added == 1
    assert text.endswith(
        "## File index\n\n- `artifacts/images/a.png`: generated image\n"
    )


def test_appends_inside_existing_section_and_skips_duplicates(tmp_path: Path) -> None:
    (tmp_path / "context.md").write_text(
        "## File index\n\n- `notes/a.md`: notes\n\n## Related knowledge\n\n- x\n"
    )
    entries = [(tmp_path / "artifacts/b.mp4", "generated video")]
    add_to_file_index(tmp_path, entries)
    assert add_to_file_index(tmp_path, entries) == 0
    assert (tmp_path / "context.md").read_text() == (
        "## File index\n\n- `notes/a.md`: notes\n"
        "- `artifacts/b.mp4`: generated video\n\n## Related knowledge\n\n- x\n"
    )


def test_creates_context_when_missing(tmp_path: Path) -> None:
    add_to_file_index(tmp_path, [(tmp_path / "artifacts/c.mp3", "speech")])
    assert (tmp_path / "context.md").read_text() == (
        "## File index\n\n- `artifacts/c.mp3`: speech\n"
    )


def test_unindexed_artifacts(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    (artifacts / "images").mkdir(parents=True)
    for name in ("images/a.png", "report.md", "job.json", ".hidden"):
        (artifacts / name).write_text("x")
    (tmp_path / "context.md").write_text("- `artifacts/report.md`: report\n")
    assert unindexed_artifacts(tmp_path) == [artifacts / "images/a.png"]
    assert unindexed_artifacts(tmp_path / "missing") == []
