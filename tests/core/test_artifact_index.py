import json
import os

from suzent.config import CONFIG
from suzent.core import artifact_index


def _tool(name: str, paths: list[str], success: bool = True) -> dict:
    return {
        "type": "tool",
        "toolName": name,
        "state": "completed",
        "output": json.dumps(
            {"success": success, "message": "ok", "metadata": {"saved_paths": paths}}
        ),
    }


def _assistant(*parts: dict, **extra) -> dict:
    return {"role": "assistant", "content": "", "parts": list(parts), **extra}


def test_transcript_outputs_keeps_deliverables_only() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        _assistant(
            _tool("generate_image", ["/workspace/artifacts/images/cat.png"]),
            _tool("analyze_visual", ["/workspace/photo.png"]),
            _tool("edit_image", ["/workspace/failed.png"], success=False),
            _tool("send_file", ["/repo/report.pdf"], success=False),
            file_changes=[
                {"path": "/p/artifacts/brief.md"},
                {"path": "/p/notes.md"},
                {"path": "/p/artifacts/gone.md", "after_exists": False},
            ],
        ),
        _assistant(file_changes_undone=True, file_changes=[{"path": "/p/artifacts/x"}]),
    ]

    assert artifact_index.transcript_outputs(messages) == [
        "/workspace/artifacts/images/cat.png",
        "/repo/report.pdf",
        "/p/artifacts/brief.md",
    ]


def test_index_groups_files_by_project_and_links_their_chat(
    temp_db, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path / "sandbox"))
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)

    poster_id = temp_db.create_project("Poster", "poster")
    library = tmp_path / "sandbox" / "projects" / "poster" / "artifacts"
    (library / "images").mkdir(parents=True)
    cat = library / "images" / "cat.png"
    cat.write_bytes(b"png")
    notes = library / "notes.md"
    notes.write_text("by hand")
    (library / ".hidden").write_text("skip")
    os.utime(notes, (1, 1))

    elsewhere = tmp_path / "repo" / "report.pdf"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"pdf")

    chat_id = temp_db.create_chat(
        "Make a poster",
        {},
        messages=[
            _assistant(
                _tool("generate_image", ["/workspace/artifacts/images/cat.png"]),
                _tool("send_file", [str(elsewhere)]),
                _tool("send_file", [str(tmp_path / "missing.pdf")]),
            )
        ],
        project_id=poster_id,
    )

    index = artifact_index.build_artifact_index()

    by_name = {item.name: item for item in index.items}
    assert set(by_name) == {"cat.png", "report.pdf", "notes.md"}
    assert index.items[-1].name == "notes.md"
    assert by_name["cat.png"].kind == "image"
    assert by_name["cat.png"].chat_id == chat_id
    assert by_name["cat.png"].chat_title == "Make a poster"
    assert by_name["report.pdf"].path == str(elsewhere.resolve())
    assert by_name["notes.md"].chat_id is None
    assert by_name["notes.md"].serve_chat_id == chat_id
    assert {p.id: p.count for p in index.projects}[poster_id] == 3
