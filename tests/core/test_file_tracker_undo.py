from pathlib import Path

import pytest

from suzent.config import CONFIG
from suzent.core.file_tracker import FileRestoreConflictError, FileTracker


def _tracker(tmp_path: Path, monkeypatch) -> FileTracker:
    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path / "sandbox"))
    return FileTracker("chat-1")


def test_snapshot_generates_diff_and_restores_agent_change(tmp_path, monkeypatch):
    tracked = tmp_path / "example.py"
    tracked.write_text("before\n", encoding="utf-8")
    tracker = _tracker(tmp_path, monkeypatch)
    tracker.track_edit(str(tracked))
    tracked.write_text("after\nadded\n", encoding="utf-8")

    snapshot = tracker.make_snapshot()
    backup = snapshot[str(tracked)]

    assert backup.additions == 2
    assert backup.deletions == 1
    assert "-before" in backup.diff
    assert "+after" in backup.diff

    changed = FileTracker.apply_snapshot("chat-1", snapshot)

    assert changed == [str(tracked)]
    assert tracked.read_text(encoding="utf-8") == "before\n"


def test_restore_rejects_manual_change_after_agent_turn(tmp_path, monkeypatch):
    tracked = tmp_path / "example.py"
    tracked.write_text("before\n", encoding="utf-8")
    tracker = _tracker(tmp_path, monkeypatch)
    tracker.track_edit(str(tracked))
    tracked.write_text("agent\n", encoding="utf-8")
    snapshot = tracker.make_snapshot()
    tracked.write_text("manual\n", encoding="utf-8")

    with pytest.raises(FileRestoreConflictError) as exc_info:
        FileTracker.apply_snapshot("chat-1", snapshot)

    assert exc_info.value.paths == [str(tracked)]
    assert tracked.read_text(encoding="utf-8") == "manual\n"


def test_restore_recreates_file_deleted_by_agent(tmp_path, monkeypatch):
    tracked = tmp_path / "example.py"
    tracked.write_text("before\n", encoding="utf-8")
    tracker = _tracker(tmp_path, monkeypatch)
    tracker.track_edit(str(tracked))
    tracked.unlink()
    snapshot = tracker.make_snapshot()

    changed = FileTracker.apply_snapshot("chat-1", snapshot)

    assert changed == [str(tracked)]
    assert tracked.read_text(encoding="utf-8") == "before\n"


def test_restore_rejects_changed_new_file(tmp_path, monkeypatch):
    tracked = tmp_path / "new.py"
    tracker = _tracker(tmp_path, monkeypatch)
    tracker.track_edit(str(tracked))
    tracked.write_text("agent\n", encoding="utf-8")
    snapshot = tracker.make_snapshot()
    tracked.write_text("manual\n", encoding="utf-8")

    with pytest.raises(FileRestoreConflictError):
        FileTracker.apply_snapshot("chat-1", snapshot)

    assert tracked.read_text(encoding="utf-8") == "manual\n"
