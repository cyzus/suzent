from pathlib import Path

import pytest
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.database import ChatDatabase


def _client(temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from suzent.routes import chat_routes

    monkeypatch.setattr(chat_routes, "get_database", lambda: temp_db)
    return TestClient(
        Starlette(
            routes=[
                Route("/chats", chat_routes.get_chats),
                Route("/chats/{chat_id}", chat_routes.update_chat, methods=["PUT"]),
            ]
        )
    )


def test_archive_hides_chat_until_restored(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(temp_db, monkeypatch)
    kept = temp_db.create_chat("Kept", {})
    old = temp_db.create_chat("Old", {})
    project = temp_db.create_project("Work", "work")
    temp_db.link_chat_to_project(old, project)
    temp_db.update_chat(old, pinned=True)
    previous_updated_at = temp_db.get_chat(old).updated_at

    response = client.put(f"/chats/{old}", json={"archived": True})
    assert response.status_code == 200
    assert response.json()["archived"] is True
    assert response.json()["pinned"] is False
    assert temp_db.get_chat(old).updated_at == previous_updated_at

    data = client.get("/chats").json()
    assert [chat["id"] for chat in data["chats"]] == [kept]
    assert data["pinnedChats"] == []
    assert data["total"] == 1
    assert data["archivedCount"] == 1

    archived = client.get("/chats?archived=true").json()
    assert [chat["id"] for chat in archived["chats"]] == [old]
    assert archived["chats"][0]["archived"] is True
    assert archived["total"] == 1
    assert client.get(f"/chats?project_id={project}").json()["chats"] == []
    assert client.get(f"/chats?project_id={project}").json()["archivedCount"] == 1
    found = client.get("/chats?search=Old").json()["chats"]
    assert [(chat["id"], chat["archived"]) for chat in found] == [(old, True)]
    assert [
        chat["id"]
        for chat in client.get("/chats?archived=true&search=Old").json()["chats"]
    ] == [old]

    assert client.put(f"/chats/{old}", json={"archived": "no"}).status_code == 400
    assert client.put(f"/chats/{old}", json={"archived": False}).status_code == 200
    data = client.get("/chats").json()
    assert {chat["id"] for chat in data["chats"]} == {kept, old}
    assert data["archivedCount"] == 0


def test_archived_chats_leave_project_unread_counts(temp_db: ChatDatabase) -> None:
    chat_id = temp_db.create_chat("Noisy", {"unread_count": 3})
    project = temp_db.create_project("Work", "work")
    temp_db.link_chat_to_project(chat_id, project)
    assert temp_db.get_project_unread_counts() == {project: {chat_id: 3}}

    temp_db.update_chat(chat_id, archived=True)
    assert temp_db.get_project_unread_counts() == {}


def test_archive_survives_rebuild_from_logs(temp_db: ChatDatabase) -> None:
    chat_id = temp_db.create_chat("Archived", {})
    temp_db.update_chat(chat_id, archived=True)

    temp_db.engine.dispose()
    temp_db.db_path.unlink()
    rebuilt = ChatDatabase(str(temp_db.db_path))
    assert rebuilt.get_chat(chat_id).archived is True
    assert rebuilt.list_chats(archived=False) == []
    rebuilt.engine.dispose()


def test_legacy_database_gains_archived_column(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    database = ChatDatabase(str(path))
    chat_id = database.create_chat("Existing", {})
    with database.engine.begin() as connection:
        connection.execute(text("ALTER TABLE chats DROP COLUMN archived"))
    database.engine.dispose()

    migrated = ChatDatabase(str(path))
    assert migrated.get_chat(chat_id).archived is False
    migrated.update_chat(chat_id, archived=True)
    migrated.engine.dispose()

    reopened = ChatDatabase(str(path))
    assert reopened.get_chat(chat_id).archived is True
    reopened.engine.dispose()
