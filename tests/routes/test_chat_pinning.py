from pathlib import Path

import pytest
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.database import ChatDatabase


def test_pin_roundtrip_across_projects_and_pages(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import chat_routes

    monkeypatch.setattr(chat_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(
            routes=[
                Route("/chats", chat_routes.get_chats),
                Route("/chats/{chat_id}", chat_routes.update_chat, methods=["PUT"]),
            ]
        )
    )
    older = temp_db.create_chat("Older", {})
    newer = temp_db.create_chat("Newer", {})
    project = temp_db.create_project("Work", "work")
    temp_db.link_chat_to_project(older, project)
    previous_updated_at = temp_db.get_chat(older).updated_at

    response = client.put(f"/chats/{older}", json={"pinned": True})
    assert response.status_code == 200
    assert response.json()["pinned"] is True
    assert temp_db.get_chat(older).updated_at == previous_updated_at
    assert temp_db.get_chat(older).project_id == project

    data = client.get("/chats?limit=1").json()
    assert [chat["id"] for chat in data["chats"]] == [newer]
    assert [chat["id"] for chat in data["pinnedChats"]] == [older]
    assert data["pinnedChats"][0]["projectName"] == "Work"
    assert client.get("/chats?search=Newer").json()["pinnedChats"][0]["id"] == older
    assert client.put(f"/chats/{older}", json={"pinned": "false"}).status_code == 400
    assert temp_db.get_chat(older).pinned is True

    assert client.put(f"/chats/{older}", json={"title": "Renamed"}).status_code == 200
    assert client.get("/chats").json()["pinnedChats"][0]["title"] == "Renamed"
    assert client.put(f"/chats/{older}", json={"pinned": False}).status_code == 200
    assert client.get("/chats").json()["pinnedChats"] == []
    assert client.put("/chats/missing", json={"pinned": True}).status_code == 404

    temp_db.update_chat(older, pinned=True)
    temp_db.delete_chat(older)
    assert client.get("/chats").json()["pinnedChats"] == []


@pytest.mark.parametrize(
    "old_name,expected", [("Default", "Home"), ("Personal", "Personal")]
)
def test_legacy_migration_and_pin_persistence(
    tmp_path: Path, old_name: str, expected: str
) -> None:
    path = tmp_path / "legacy.db"
    database = ChatDatabase(str(path))
    home = database.get_project_by_slug("default")
    database.update_project(home.id, name=old_name)
    chat_id = database.create_chat("Existing", {})
    with database.engine.begin() as connection:
        connection.execute(text("ALTER TABLE chats DROP COLUMN pinned"))
    database.engine.dispose()

    migrated = ChatDatabase(str(path))
    assert migrated.get_project(home.id).name == expected
    assert migrated.get_chat(chat_id).pinned is False
    migrated.update_chat(chat_id, pinned=True)
    migrated.update_project(home.id, name="My Home")
    migrated.engine.dispose()

    reopened = ChatDatabase(str(path))
    assert reopened.get_project(home.id).name == "My Home"
    assert reopened.get_chat(chat_id).pinned is True
    reopened.engine.dispose()
