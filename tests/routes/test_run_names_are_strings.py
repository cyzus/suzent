"""A run's name comes from the request, so the request may have sent anything.

The chat and the token the client minted for its turn both become parts of
registry keys. A JSON client can put a list or a dict where a string belongs,
and that reaches the registry as an unhashable key: the route would raise, and
report a 500 -- on /chat/send after it had already written the user's row, so
the client sees a failure over a message the transcript now holds. A malformed
request is not a server fault; it is answered at the boundary, before anything
is stored.
"""

import json
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from suzent.core import stream_registry
from suzent.routes.chat_routes import chat_send, steer_chat_send, stop_chat


def request(payload: object, path: str) -> Request:
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(payload).encode(),
            "more_body": False,
        }

    return Request(
        {"type": "http", "method": "POST", "path": path, "headers": []}, receive
    )


@pytest.fixture(autouse=True)
def clean_registry():
    stream_registry.background_queues.clear()
    stream_registry._pending_client_stops.clear()
    yield
    stream_registry.background_queues.clear()
    stream_registry._pending_client_stops.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [["a"], {"a": 1}, 7])
async def test_a_send_whose_token_is_not_a_name_is_refused_before_it_writes(
    monkeypatch, token
):
    prewritten: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes._prewrite_user_display_message",
        lambda chat_id, message, files: prewritten.append(message),
    )

    response = await chat_send(
        request(
            {"chat_id": "c", "message": "hi", "client_run_token": token}, "/chat/send"
        )
    )

    assert response.status_code == 400
    assert prewritten == []


@pytest.mark.asyncio
async def test_a_steer_whose_token_is_not_a_name_is_refused(monkeypatch):
    monkeypatch.setattr(
        "suzent.routes.chat_routes._prewrite_user_display_message",
        MagicMock(),
    )

    response = await steer_chat_send(
        request(
            {"chat_id": "c", "message": "hi", "client_run_token": ["a"]},
            "/chat/steer-send",
        )
    )

    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["chat_id", "run_id"])
async def test_a_stop_whose_names_are_not_names_is_refused(field):
    payload = {"chat_id": "c", "run_id": "r"}
    payload[field] = {"not": "a name"}

    response = await stop_chat(request(payload, "/chat/stop"))

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_a_stop_naming_the_empty_string_is_refused(monkeypatch):
    """An empty name is not the same as sending no name.

    Every reader tests the name for truth, so `run_id: ""` reads as a stop that
    named nothing -- and a stop that names nothing cancels whatever turn the
    chat is running, which is exactly what naming a run protects against.
    """
    stopped: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: stopped.append(chat_id) or True,
    )
    stream_registry.register_background_stream("c")

    response = await stop_chat(request({"chat_id": "c", "run_id": ""}, "/chat/stop"))

    assert response.status_code == 400
    assert stopped == []


@pytest.mark.asyncio
async def test_a_send_whose_token_is_the_empty_string_is_refused(monkeypatch):
    monkeypatch.setattr(
        "suzent.routes.chat_routes._prewrite_user_display_message", MagicMock()
    )

    response = await chat_send(
        request({"chat_id": "c", "message": "hi", "client_run_token": ""}, "/chat/send")
    )

    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [["stop"], {"why": "stop"}, 7])
async def test_a_stop_whose_reason_is_not_text_is_refused(reason):
    """The reason becomes a frame's message, and that message is typed.

    Carried this far it raises inside the producer instead, and the client that
    asked to stop is answered with a generic failure in place of the tagged
    stop and the clean ending this route promises.
    """
    response = await stop_chat(
        request({"chat_id": "c1", "reason": reason}, "/chat/stop")
    )

    assert response.status_code == 400
