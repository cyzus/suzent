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
        lambda chat_id, reason, expect_run=None: stopped.append(chat_id) or True,
    )
    stream_registry.register_background_stream("chat")

    response = await stop_chat(request({"chat_id": "chat", "run_id": "an-older-run"}))

    assert response.status_code == 409
    assert stopped == []


async def test_a_stop_for_the_current_run_goes_through(monkeypatch):
    stopped: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: stopped.append(chat_id) or True,
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
        lambda chat_id, reason, expect_run=None: stopped.append(chat_id) or True,
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
        lambda chat_id, reason, expect_run=None: stopped.append(chat_id) or True,
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
        lambda chat_id, reason, expect_run=None: stopped.append(chat_id) or True,
    )
    queue = stream_registry.register_background_stream("chat")
    queue.replay.client_token = "the-turn-that-replaced-it"

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": "a-token-from-before"})
    )

    assert response.status_code == 409
    assert stopped == []


async def test_a_stop_in_the_steer_window_is_kept_for_the_run_it_named(monkeypatch):
    """The named run exists but has not taken the chat's control yet.

    /chat/steer-send registers the replacement run's replay, then cancels the
    turn it replaces, and only then starts the new one. A stop landing in that
    gap matches the new run by name while the control still belongs to the old
    turn, so cancelling whatever control is there would stop the wrong turn and
    report success. Keep it for the run that was named instead.
    """
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )

    class _NothingRunning:
        async def cancel(self, chat_id):
            return False

    monkeypatch.setattr("suzent.acp.get_acp_manager", lambda: _NothingRunning())
    queue = stream_registry.register_background_stream("chat")

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": queue.replay.run_id})
    )

    assert response.status_code == 200
    assert json.loads(bytes(response.body))["stream_stopped"] is True
    assert queue.replay.stop_requested == "Stream stopped by user"


async def test_a_stop_for_a_finished_run_is_not_kept(monkeypatch):
    """Nothing is coming to take it, so this is a miss like any other."""
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )

    class _NothingRunning:
        async def cancel(self, chat_id):
            return False

    monkeypatch.setattr("suzent.acp.get_acp_manager", lambda: _NothingRunning())
    queue = stream_registry.register_background_stream("chat")
    queue.put_nowait(None)

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": queue.replay.run_id})
    )

    assert response.status_code == 404
    assert queue.replay.stop_requested is None


async def test_an_acp_stop_in_the_steer_window_does_not_cancel_the_old_prompt(
    monkeypatch,
):
    """`AcpManager.cancel` cancels the session, not a run.

    An ACP steer registers the replacement replay and then cancels the prompt
    it replaces. A stop naming the replacement in that window must not be
    answered by cancelling the session -- that stops the turn being replaced
    and reports the stop as applied while the replacement goes on to run.
    """
    cancelled: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )

    class _Session:
        async def cancel(self, chat_id):
            cancelled.append(chat_id)
            return True

    monkeypatch.setattr("suzent.acp.get_acp_manager", lambda: _Session())
    queue = stream_registry.register_background_stream("chat")

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": queue.replay.run_id})
    )

    assert response.status_code == 200
    assert cancelled == []
    assert queue.replay.stop_requested == "Stream stopped by user"


async def test_an_acp_stop_for_the_running_prompt_cancels_the_session(monkeypatch):
    cancelled: list[str] = []
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )

    class _Session:
        async def cancel(self, chat_id):
            cancelled.append(chat_id)
            return True

    monkeypatch.setattr("suzent.acp.get_acp_manager", lambda: _Session())
    queue = stream_registry.register_background_stream("chat")
    # The ACP turn is under way: its prompt is the one the session is running.
    queue.replay.producer_started = True

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": queue.replay.run_id})
    )

    assert response.status_code == 200
    assert cancelled == ["chat"]
    assert queue.replay.stop_requested is None


async def test_an_acp_stop_the_session_refuses_is_not_kept_for_a_live_run(monkeypatch):
    """A failed stop is news the client can act on; a false acceptance is not.

    The run is already producing, so it is past every point that reads a
    deferred mark -- leaving one there would report a stop that nothing carries
    out, and the client would wait out its ten seconds while the agent keeps
    going with its tools.
    """
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )

    class _Session:
        async def cancel(self, chat_id):
            return False

    monkeypatch.setattr("suzent.acp.get_acp_manager", lambda: _Session())
    queue = stream_registry.register_background_stream("chat")
    queue.replay.producer_started = True

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": queue.replay.run_id})
    )

    assert response.status_code == 404
    assert queue.replay.stop_requested is None
