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
    stream_registry._pending_client_stops.clear()
    yield
    stream_registry.background_queues.clear()
    stream_registry._pending_client_stops.clear()


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


async def test_a_stop_is_not_kept_for_a_run_that_replaced_the_one_it_named(monkeypatch):
    """The replacement registers itself while the ACP cancellation is awaited.

    Looking the replay up again here would leave the stop on the newcomer -- a
    run this stop never named, which would cancel itself the moment it started
    while the endpoint reported the stale stop as applied.
    """
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )
    queue = stream_registry.register_background_stream("chat")
    queue.replay.producer_started = True
    replacement: list[object] = []

    class _Session:
        async def cancel(self, chat_id):
            # The redirect lands while this cancellation is in flight.
            replacement.append(stream_registry.register_background_stream(chat_id))
            return False

    monkeypatch.setattr("suzent.acp.get_acp_manager", lambda: _Session())

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": queue.replay.run_id})
    )

    assert response.status_code == 404
    assert queue.replay.stop_requested is None
    assert replacement[0].replay.stop_requested is None


async def test_a_stop_for_a_run_that_has_not_registered_yet_is_kept(monkeypatch):
    """The Stop button is live before the start request has been read.

    A recoverable turn outlives the connection that asked for it, so the
    browser abandoning its own request does not stop it. Keeping the stop under
    the name the client minted is what does: the run takes it as it registers.
    """
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )

    response = await stop_chat(request({"chat_id": "chat", "run_id": "not-here-yet"}))

    assert response.status_code == 200
    assert json.loads(bytes(response.body))["stream_stopped"] is True

    # The start lands afterwards and the run cancels itself on arrival.
    queue = stream_registry.register_background_stream("chat")
    stream_registry.attach_client_token("chat", queue.replay, "not-here-yet")
    assert queue.replay.stop_requested == "Stream stopped by user"


async def test_a_run_that_registers_under_another_name_keeps_running(monkeypatch):
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )

    await stop_chat(request({"chat_id": "chat", "run_id": "a-turn-that-never-came"}))

    queue = stream_registry.register_background_stream("chat")
    stream_registry.attach_client_token("chat", queue.replay, "some-other-turn")
    assert queue.replay.stop_requested is None


async def test_a_remembered_stop_does_not_reach_a_turn_minutes_later(monkeypatch):
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: False,
    )
    await stop_chat(request({"chat_id": "chat", "run_id": "slow-start"}))

    later = stream_registry.time.monotonic() + stream_registry.PENDING_CLIENT_STOP_TTL
    monkeypatch.setattr(stream_registry.time, "monotonic", lambda: later + 60.0)
    queue = stream_registry.register_background_stream("chat")
    stream_registry.attach_client_token("chat", queue.replay, "slow-start")

    assert queue.replay.stop_requested is None


async def test_a_stop_for_a_replacement_that_has_not_registered_survives_the_refusal(
    monkeypatch,
):
    """Stale for the run that is producing is not stale for the one named.

    A /chat/steer-send start that has not been read yet has registered nothing,
    so the turn it replaces is still the one producing and this stop cannot be
    applied to it. But the replacement is on its way, and the client has already
    given up waiting -- abandoning its request does not stop a recoverable turn.
    Answer stale, keep the name, and let the replacement take it on arrival.
    """
    monkeypatch.setattr(
        "suzent.routes.chat_routes.stop_stream",
        lambda chat_id, reason, expect_run=None: True,
    )
    old = stream_registry.register_background_stream("chat")
    assert old.producer_active

    response = await stop_chat(
        request({"chat_id": "chat", "run_id": "token-for-the-steer"})
    )

    assert response.status_code == 409
    assert old.replay.stop_requested is None

    replacement = stream_registry.register_background_stream("chat")
    stream_registry.attach_client_token(
        "chat", replacement.replay, "token-for-the-steer"
    )

    assert replacement.replay.stop_requested == "Stream stopped by user"
