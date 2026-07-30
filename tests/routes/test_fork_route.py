import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes.chat_routes import fork_chat_route


def test_fork_route_returns_new_chat_and_restore_count(monkeypatch):
    monkeypatch.setattr(
        "suzent.core.fork.fork_chat",
        lambda chat_id, title=None, message_index=None: (
            f"{chat_id}-fork",
            ["one.py", "two.py"],
        ),
    )
    app = Starlette(
        routes=[
            Route(
                "/api/chats/{chat_id}/fork",
                fork_chat_route,
                methods=["POST"],
            )
        ]
    )

    response = TestClient(app).post(
        "/api/chats/chat-1/fork",
        json={"message_index": 4},
    )

    assert response.status_code == 200
    assert response.json() == {
        "new_chat_id": "chat-1-fork",
        "restored_files_count": 2,
    }


def test_fork_route_reports_invalid_history_point(monkeypatch):
    def reject_fork(*_args, **_kwargs):
        raise ValueError("up_to_message_index is outside the message history")

    monkeypatch.setattr("suzent.core.fork.fork_chat", reject_fork)
    app = Starlette(
        routes=[
            Route(
                "/api/chats/{chat_id}/fork",
                fork_chat_route,
                methods=["POST"],
            )
        ]
    )

    response = TestClient(app).post(
        "/api/chats/chat-1/fork",
        json={"message_index": 100},
    )

    assert response.status_code == 409
    assert "outside the message history" in response.json()["error"]


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"message_index": "4"},
        {"message_index": True},
        {"message_index": 0},
        {"unknown": "value"},
    ],
)
def test_fork_route_rejects_invalid_payloads(monkeypatch, body):
    def unexpected_fork(*_args, **_kwargs):
        raise AssertionError("fork_chat should not be called")

    monkeypatch.setattr("suzent.core.fork.fork_chat", unexpected_fork)
    app = Starlette(
        routes=[
            Route(
                "/api/chats/{chat_id}/fork",
                fork_chat_route,
                methods=["POST"],
            )
        ]
    )

    client = TestClient(app)
    response = (
        client.post(
            "/api/chats/chat-1/fork",
            content="null",
            headers={"Content-Type": "application/json"},
        )
        if body is None
        else client.post("/api/chats/chat-1/fork", json=body)
    )

    assert response.status_code == 422
    assert response.json()["error"] == "Invalid fork request"
