"""A stop names the run it meant to stop.

Cancellation is applied to whatever control the chat currently has, so a stop
request still in transit when the user redirects would land on the replacement
turn and cancel that one instead. The client can retire its own attempt, but it
cannot call back a cancellation the server has already applied.

The name is either the run_id the backend assigned, once a protocol frame has
carried it to the client, or the token the client minted when it asked for the
turn -- which is the only name available while the Stop button is already live
and the first frame has not arrived.
"""

import json

import pytest
from starlette.requests import Request

from suzent.core import stream_registry
from suzent.routes.chat_routes import stop_chat


def request(payload: object) -> Request:
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(payload).encode(),
            "more_body": False,
        }

    return Request(
        {"type": "http", "method": "POST", "path": "/chat/stop", "headers": []}, receive
    )


@pytest.fixture(autouse=True)
def clean_registry():
    stream_registry.background_queues.clear()
    yield
    stream_registry.background_queues.clear()


async def test_a_stop_for_a_run_that_is_gone_is_refused(monkeypatch):
    stopped: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason: stopped.append(chat_id) or True,
    )
    stream_registry.register_background_stream("chat")

    response = await stop_chat(request({"chat_id": "chat", "run_id": "an-older-run"}))

    assert response.status_code == 409
    assert stopped == []


async def test_a_stop_for_the_current_run_goes_through(monkeypatch):
    stopped: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason: stopped.append(chat_id) or True,
    )
    queue = stream_registry.register_background_stream("chat")

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": queue.replay.run_id})
    )

    assert response.status_code == 200
    assert stopped == ["chat"]


async def test_a_stop_without_a_run_id_still_works(monkeypatch):
    """An older client, or a turn the client never saw a run_id for."""
    stopped: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason: stopped.append(chat_id) or True,
    )
    stream_registry.register_background_stream("chat")

    response = await stop_chat(request({"chat_id": "chat"}))

    assert response.status_code == 200
    assert stopped == ["chat"]


async def test_a_stop_naming_the_token_the_client_minted_goes_through(monkeypatch):
    """The Stop button is live before the first frame carries a run_id."""
    stopped: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason: stopped.append(chat_id) or True,
    )
    queue = stream_registry.register_background_stream("chat")
    queue.replay.client_token = "token-for-this-turn"

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": "token-for-this-turn"})
    )

    assert response.status_code == 200
    assert stopped == ["chat"]


async def test_a_stop_naming_a_token_from_the_previous_turn_is_refused(monkeypatch):
    stopped: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason: stopped.append(chat_id) or True,
    )
    queue = stream_registry.register_background_stream("chat")
    queue.replay.client_token = "the-turn-that-replaced-it"

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": "a-token-from-before"})
    )

    assert response.status_code == 409
    assert stopped == []
