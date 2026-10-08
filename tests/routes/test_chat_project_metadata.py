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


def test_project_unread_counts_include_all_chats_and_follow_moves(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import project_routes

    monkeypatch.setattr(project_routes, "get_database", lambda: temp_db)
    client = TestClient(
        Starlette(routes=[Route("/projects", project_routes.list_projects)])
    )
    project_id = temp_db.create_project("Work", "work")
    other_project_id = temp_db.create_project("Other", "other")
    older = temp_db.create_chat("Older", {"unread_count": 2})
    newer = temp_db.create_chat("Newer", {"unread_count": 1})
    temp_db.link_chat_to_project(older, project_id)
    temp_db.link_chat_to_project(newer, project_id)

    def counts() -> dict[str, dict[str, int]]:
        response = client.get("/projects")
        assert response.status_code == 200
        return {p["id"]: p["unreadChatCounts"] for p in response.json()}

    assert counts()[project_id] == {older: 2, newer: 1}
    temp_db.mark_chat_read(older)
    assert counts()[project_id] == {newer: 1}
    temp_db.link_chat_to_project(newer, other_project_id)
    assert counts()[project_id] == {}
    assert counts()[other_project_id] == {newer: 1}
