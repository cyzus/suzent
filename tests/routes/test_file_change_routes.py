from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.core.file_tracker import FileRestoreConflictError, FileTracker
from suzent.routes.chat_routes import get_chat_file_changes, undo_chat_files


def test_file_changes_returns_diff_summary(monkeypatch):
    checkpoint = SimpleNamespace(
        file_snapshot=[
            {
                "path": "example.py",
                "diff": "-before\n+after\n",
                "additions": 1,
                "deletions": 1,
            }
        ]
    )
    monkeypatch.setattr(
        "suzent.core.retry.load_retry_checkpoint",
        lambda _chat_id: checkpoint,
    )
    app = Starlette(
        routes=[
            Route(
                "/api/chats/{chat_id}/file-changes",
                get_chat_file_changes,
                methods=["GET"],
            )
        ]
    )

    response = TestClient(app).get("/api/chats/chat-1/file-changes")

    assert response.status_code == 200
    assert response.json()["additions"] == 1
    assert response.json()["files"][0]["path"] == "example.py"


def test_undo_route_reports_conflicting_manual_changes(monkeypatch):
    checkpoint = SimpleNamespace(file_snapshot=[{"path": "example.py"}])
    monkeypatch.setattr(
        "suzent.core.retry.load_retry_checkpoint",
        lambda _chat_id: checkpoint,
    )
    monkeypatch.setattr(FileTracker, "snapshot_from_json", lambda _data: {})

    def raise_conflict(_chat_id, _snapshot):
        raise FileRestoreConflictError(["example.py"])

    monkeypatch.setattr(FileTracker, "apply_snapshot", raise_conflict)
    app = Starlette(
        routes=[
            Route(
                "/api/chats/{chat_id}/undo",
                undo_chat_files,
                methods=["POST"],
            )
        ]
    )

    response = TestClient(app).post("/api/chats/chat-1/undo")

    assert response.status_code == 409
    assert response.json()["conflicts"] == ["example.py"]


def test_undo_route_uses_requested_message_snapshot(monkeypatch):
    stored_snapshot = [{"path": "historical.py", "backup_name": "backup-v1"}]
    chat = SimpleNamespace(
        messages=[
            {"role": "user", "content": "change it"},
            {
                "role": "assistant",
                "content": "done",
                "file_changes": stored_snapshot,
            },
            {"role": "assistant", "content": "no file edits"},
        ]
    )
    database = SimpleNamespace(get_chat=lambda _chat_id: chat)
    monkeypatch.setattr("suzent.routes.chat_routes.get_database", lambda: database)
    monkeypatch.setattr(
        FileTracker, "snapshot_from_json", lambda data: {"snapshot": data}
    )
    applied = {}

    def apply_snapshot(chat_id, snapshot):
        applied["chat_id"] = chat_id
        applied["snapshot"] = snapshot
        return ["historical.py"]

    monkeypatch.setattr(FileTracker, "apply_snapshot", apply_snapshot)
    app = Starlette(
        routes=[
            Route(
                "/api/chats/{chat_id}/undo",
                undo_chat_files,
                methods=["POST"],
            )
        ]
    )

    response = TestClient(app).post("/api/chats/chat-1/undo", json={"message_index": 1})

    assert response.status_code == 200
    assert response.json()["changed_files"] == ["historical.py"]
    assert applied == {
        "chat_id": "chat-1",
        "snapshot": {"snapshot": stored_snapshot},
    }
