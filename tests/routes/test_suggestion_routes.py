from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes import suggestion_routes


def _client() -> TestClient:
    app = Starlette(
        routes=[
            Route(
                "/chat/input-suggestion",
                suggestion_routes.get_input_suggestion,
                methods=["POST"],
            ),
            Route(
                "/chat/input-suggestion",
                suggestion_routes.get_saved_input_suggestion,
                methods=["GET"],
            ),
        ]
    )
    return TestClient(app)


def test_input_suggestion_returns_prediction(monkeypatch):
    received: list[list[dict]] = []

    async def fake_suggest(messages):
        received.append(messages)
        return "Now make it shorter"

    monkeypatch.setattr(suggestion_routes, "suggest_next_input", fake_suggest)

    response = _client().post(
        "/chat/input-suggestion",
        json={
            "messages": [
                {"role": "user", "content": "Draft an email"},
                {"role": "assistant", "content": "Here is a draft."},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"suggestion": "Now make it shorter"}
    assert received[0][1] == {"role": "assistant", "content": "Here is a draft."}


def test_input_suggestion_rejects_malformed_body():
    response = _client().post("/chat/input-suggestion", json={"messages": "nope"})

    assert response.status_code == 400


class _FakeDb:
    def __init__(self) -> None:
        self.saved: dict[str, tuple[str, str | None]] = {}

    def set_input_suggestion(self, chat_id, reply_key, text):
        self.saved[chat_id] = (reply_key, text)

    def get_input_suggestion(self, chat_id):
        reply_key, text = self.saved.get(chat_id, (None, None))
        if text is None:
            return None
        return type("Saved", (), {"reply_key": reply_key, "text": text})()


def test_input_suggestion_is_saved_for_the_chat_and_read_back(monkeypatch):
    db = _FakeDb()

    async def fake_suggest(messages):
        return "Now make it shorter"

    monkeypatch.setattr(suggestion_routes, "suggest_next_input", fake_suggest)
    monkeypatch.setattr(suggestion_routes, "get_database", lambda: db)
    client = _client()

    client.post(
        "/chat/input-suggestion",
        json={
            "messages": [{"role": "assistant", "content": "Here is a draft."}],
            "chat_id": "chat-1",
            "reply_key": "16:abc",
        },
    )
    response = client.get("/chat/input-suggestion", params={"chat_id": "chat-1"})

    assert response.json() == {
        "reply_key": "16:abc",
        "suggestion": "Now make it shorter",
    }
    assert client.get(
        "/chat/input-suggestion", params={"chat_id": "chat-2"}
    ).json() == {"reply_key": None, "suggestion": None}
