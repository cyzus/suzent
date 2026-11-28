import uuid

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.database import ChatDatabase


@pytest.fixture
def client(temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from suzent.routes import chat_routes

    monkeypatch.setattr(chat_routes, "get_database", lambda: temp_db)
    return TestClient(
        Starlette(routes=[Route("/chats", chat_routes.create_chat, methods=["POST"])])
    )


def test_a_chat_can_be_created_under_an_id_handed_out_earlier(
    client: TestClient, temp_db: ChatDatabase
) -> None:
    chat_id = str(uuid.uuid4())
    response = client.post("/chats", json={"id": chat_id, "title": "ACP"})
    assert response.status_code == 201
    assert response.json()["id"] == chat_id
    assert temp_db.get_chat(chat_id).title == "ACP"

    again = client.post("/chats", json={"id": chat_id, "title": "Twice"})
    assert again.status_code == 409
    assert temp_db.get_chat(chat_id).title == "ACP"


def test_a_malformed_chat_id_is_refused(client: TestClient) -> None:
    assert client.post("/chats", json={"id": "../x", "title": "Bad"}).status_code == 400
