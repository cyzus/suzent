import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.database import ChatDatabase


def test_chat_detail_reports_current_project(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import chat_routes

    monkeypatch.setattr(chat_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(routes=[Route("/chats/{chat_id}", chat_routes.get_chat)])
    )
    chat_id = temp_db.create_chat("Running chat", {})
    project_id = temp_db.create_project("Work", "work")
    temp_db.link_chat_to_project(chat_id, project_id)

    response = client.get(f"/chats/{chat_id}")
    assert response.status_code == 200
    assert response.json()["projectId"] == project_id

    other_project_id = temp_db.create_project("Other", "other")
    temp_db.link_chat_to_project(chat_id, other_project_id)
    assert client.get(f"/chats/{chat_id}").json()["projectId"] == other_project_id
