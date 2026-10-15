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
            )
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
