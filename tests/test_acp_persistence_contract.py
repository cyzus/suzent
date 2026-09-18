"""An ACP turn must claim the same persistence contract as the native runtime.

`StreamReplay.persisted` is True when no producer attached a persistence
future, so a turn that dies before writing its assistant row would otherwise
still end with STREAM_END{persisted:true} — and the client replaces what it is
showing with that snapshot.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suzent.acp.runtime import stream_acp_steer, stream_acp_turn
from suzent.core.stream_registry import background_queues, register_background_stream


def _managed(session_id="s-1"):
    managed = MagicMock()
    managed.agent_id = "claude-code"
    managed.session_id = session_id
    managed.cwd = "/tmp"
    managed.resumed = True
    managed.restored = False
    managed.updates = asyncio.Queue()
    return managed


def _text_chunk(text):
    return {
        "sessionId": "s-1",
        "update": {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": text},
        },
    }


async def _run_turn(
    chat_id,
    updates,
    result,
    *,
    append_result=True,
    replay=None,
    steer=False,
    on_ensure=None,
    on_create=None,
    prompted=None,
    restored=False,
):
    managed = _managed()
    managed.restored = restored
    results = list(result) if isinstance(result, list) else None

    async def prompt(session_id, message):
        if prompted is not None:
            prompted.append(message)
        for item in updates:
            managed.updates.put_nowait(item)
        return results.pop(0) if results else result

    managed.client.prompt = prompt

    with (
        patch("suzent.acp.runtime.get_database") as get_db,
        patch("suzent.acp.runtime.get_acp_manager") as get_manager,
    ):
        chat = MagicMock()
        chat.config = {
            "runtime": "acp",
            "acp_agent_id": "claude-code",
            "acp_session_id": "s-1",
        }
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        db.append_chat_message.return_value = append_result
        get_db.return_value = db

        manager = AsyncMock()

        async def ensure(*args, **kwargs):
            if on_ensure is not None:
                on_ensure()
            return managed

        manager.ensure.side_effect = ensure

        async def create(*args, **kwargs):
            # The rebuilt session is not a restored one, so one retry only.
            managed.restored = False
            if on_create is not None:
                on_create()
            return managed

        manager.create.side_effect = create
        get_manager.return_value = manager

        turn = (
            stream_acp_steer(chat_id, "hi", replay=replay)
            if steer
            else stream_acp_turn(chat_id, "hi", replay=replay)
        )
        chunks = [c async for c in turn]
        return chunks, db


@pytest.fixture
def queue():
    chat_id = "chat-persistence"
    q = register_background_stream(chat_id)
    try:
        yield chat_id, q
    finally:
        background_queues.pop(chat_id, None)


@pytest.mark.asyncio
async def test_persisted_only_after_the_assistant_row_is_written(queue):
    chat_id, q = queue
    chunks, db = await _run_turn(
        chat_id, [_text_chunk("hello")], {"stopReason": "end_turn"}, replay=q.replay
    )

    roles = [c.args[1]["role"] for c in db.append_chat_message.call_args_list]
    assert "assistant" in roles
    assert q.replay.persistence is not None
    assert q.replay.persistence.result() is True
    # `persisted` also wants the replay closed; the future is the part this
    # runtime owns.
    for chunk in chunks:
        q.replay.append(chunk)
    q.replay.append(None)
    assert q.replay.persisted is True


@pytest.mark.asyncio
async def test_a_turn_that_never_writes_reports_not_persisted(queue):
    chat_id, q = queue
    chunks, db = await _run_turn(
        chat_id, [], {"stopReason": "end_turn"}, replay=q.replay
    )

    assert json.loads(chunks[-1][6:])["type"] == "RUN_ERROR" or any(
        "RUN_ERROR" in c for c in chunks
    )
    roles = [c.args[1]["role"] for c in db.append_chat_message.call_args_list]
    assert "assistant" not in roles
    assert q.replay.persistence is not None
    assert q.replay.persistence.result() is False
    for chunk in chunks:
        q.replay.append(chunk)
    q.replay.append(None)
    assert q.replay.persisted is False


@pytest.mark.asyncio
async def test_a_chat_that_does_not_exist_is_not_persisted(queue):
    """The early return happens before the turn ever starts — it still counts."""
    chat_id, q = queue
    with patch("suzent.acp.runtime.get_database") as get_db:
        db = MagicMock()
        db.get_chat.return_value = None
        get_db.return_value = db
        chunks = [c async for c in stream_acp_turn(chat_id, "hi", replay=q.replay)]

    assert any("Chat not found" in c for c in chunks)
    assert q.replay.persistence is not None
    assert q.replay.persistence.result() is False


@pytest.mark.asyncio
async def test_an_append_that_found_no_chat_is_not_persisted(queue):
    """append_chat_message returns False for a chat deleted mid-turn."""
    chat_id, q = queue
    chunks, db = await _run_turn(
        chat_id,
        [_text_chunk("hello")],
        {"stopReason": "end_turn"},
        append_result=False,
        replay=q.replay,
    )

    assert q.replay.persistence is not None
    assert q.replay.persistence.result() is False
    for chunk in chunks:
        q.replay.append(chunk)
    q.replay.append(None)
    assert q.replay.persisted is False


@pytest.mark.asyncio
async def test_a_turn_with_no_replay_leaves_the_registry_alone(queue):
    """A turn that owns no replay must not claim whatever the chat has.

    An agent-inbox delivery or a sub-agent runs `run_acp_turn_text(..., None)`,
    and the registry can hand out a replay that is either a finished turn's,
    kept for a late /chat/live subscriber, or another producer's live one.
    Either way its persistence belongs to that turn, not this one.
    """
    chat_id, q = queue
    settled: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    settled.set_result(True)
    q.replay.persistence = settled

    await _run_turn(chat_id, [], {"stopReason": "end_turn"})

    assert q.replay.persistence is settled
    assert q.replay.persistence.result() is True


@pytest.mark.asyncio
async def test_a_steered_turn_claims_the_contract_too(queue):
    """A steer is cancel + re-prompt, and the re-prompt is a turn like any other.

    /chat/steer-send registers a replay for it, so a steer that dies before
    writing its assistant row must report `persisted: false` rather than
    letting the client accept a snapshot without that turn in it.
    """
    chat_id, q = queue
    with patch("suzent.acp.runtime.get_acp_manager") as get_manager:
        get_manager.return_value = AsyncMock()
        await _run_turn(
            chat_id, [], {"stopReason": "end_turn"}, replay=q.replay, steer=True
        )

    assert q.replay.persistence is not None
    assert q.replay.persistence.result() is False


@pytest.mark.asyncio
async def test_a_turn_stopped_before_its_first_token_is_persisted(queue):
    """A stop is an ending the client waits for, not a failed write.

    Nothing was produced, so nothing is missing from the database and the
    contract is met. Reporting False would end the stop the client just
    accepted as "Stream persistence failed".
    """
    chat_id, q = queue
    chunks, db = await _run_turn(
        chat_id, [], {"stopReason": "cancelled"}, replay=q.replay
    )

    roles = [c.args[1]["role"] for c in db.append_chat_message.call_args_list]
    assert "assistant" not in roles
    assert q.replay.persistence is not None
    assert q.replay.persistence.result() is True
    for chunk in chunks:
        q.replay.append(chunk)
    q.replay.append(None)
    assert q.replay.persisted is True


@pytest.mark.asyncio
async def test_a_turn_handed_a_stop_before_it_started_ends_stopped(queue):
    """A steer's replacement run can be stopped before it exists to be stopped.

    The steer route registers this run's replay and then cancels the turn it
    replaces; a stop in that window is accepted against this run and left on
    the replay. The turn has to honour it the way the native path does -- as a
    stop, tagged, with the persistence contract met because nothing was
    produced.
    """
    chat_id, q = queue
    q.replay.stop_requested = "Stream stopped by user"

    chunks, db = await _run_turn(
        chat_id, [_text_chunk("hello")], {"stopReason": "end_turn"}, replay=q.replay
    )

    # The turn ran nothing -- but the prompt the user sent is still stored, or
    # the reload a stop is followed by would come back without it. Nothing from
    # the agent is written, because the agent was never prompted.
    roles = [c.args[1]["role"] for c in db.append_chat_message.call_args_list]
    assert roles == ["user"]
    event = json.loads(chunks[-1][6:])
    assert event["type"] == "RUN_ERROR"
    assert event["code"] == "stream_stopped"
    assert q.replay.stop_requested is None
    assert q.replay.persistence.result() is True
    for chunk in chunks:
        q.replay.append(chunk)
    q.replay.append(None)
    assert q.replay.persisted is True


@pytest.mark.asyncio
async def test_a_stop_whose_prompt_could_not_be_stored_is_not_persisted(queue):
    """The stop's contract is the prompt row; a failed write breaks it.

    `persisted: true` sends the client to a reload it trusts over what it is
    showing. If the row never landed -- a chat deleted mid-turn, a database
    that refused the write -- that reload comes back without the message the
    user just sent, and the optimistic copy on screen is replaced by nothing.
    """
    chat_id, q = queue
    q.replay.stop_requested = "Stream stopped by user"

    chunks, db = await _run_turn(
        chat_id,
        [],
        {"stopReason": "end_turn"},
        append_result=False,
        replay=q.replay,
    )

    event = json.loads(chunks[-1][6:])
    assert event["code"] == "stream_stopped"
    assert q.replay.persistence.result() is False
    for chunk in chunks:
        q.replay.append(chunk)
    q.replay.append(None)
    assert q.replay.persisted is False


@pytest.mark.asyncio
async def test_a_stop_during_session_connect_is_taken_before_the_prompt(queue):
    """Connecting the agent is the window a stop is most likely to land in.

    Nothing can cancel the turn yet -- there is no prompt -- so the route leaves
    the stop on the replay. The turn has to take it at the prompt, or the user
    would watch the agent answer a turn they already stopped.
    """
    chat_id, q = queue
    prompted: list[str] = []

    def on_ensure():
        # The run must not claim to be live before it has a prompt to cancel;
        # the route reads exactly this to decide between cancelling the ACP
        # session and leaving the stop here.
        assert q.replay.producer_started is False
        q.replay.stop_requested = "Stream stopped by user"

    chunks, db = await _run_turn(
        chat_id,
        [_text_chunk("hello")],
        {"stopReason": "end_turn"},
        replay=q.replay,
        on_ensure=on_ensure,
        prompted=prompted,
    )

    assert prompted == []
    roles = [c.args[1]["role"] for c in db.append_chat_message.call_args_list]
    assert roles == ["user"]
    event = json.loads(chunks[-1][6:])
    assert event["type"] == "RUN_ERROR"
    assert event["code"] == "stream_stopped"
    assert q.replay.stop_requested is None
    assert q.replay.persistence.result() is True


@pytest.mark.asyncio
async def test_a_turn_that_reaches_its_prompt_declares_the_run_live(queue):
    """The other half of the same rule: once prompted, the session can be cut."""
    chat_id, q = queue
    seen: list[bool] = []

    await _run_turn(
        chat_id,
        [_text_chunk("hello")],
        {"stopReason": "end_turn"},
        replay=q.replay,
        on_ensure=lambda: seen.append(q.replay.producer_started),
    )

    assert seen == [False]
    assert q.replay.producer_started is True


@pytest.mark.asyncio
async def test_a_stop_whose_prompt_was_refused_mid_turn_is_not_persisted(queue):
    """Same contract at the other stop: the one the agent itself reports.

    The turn reached the agent and was cancelled before its first token, so the
    user's row is the whole of what this turn had to store. If that write was
    refused, the reload `persisted: true` sends the client to comes back
    without the prompt.
    """
    chat_id, q = queue
    chunks, db = await _run_turn(
        chat_id,
        [],
        {"stopReason": "cancelled"},
        append_result=False,
        replay=q.replay,
    )

    event = json.loads(chunks[-1][6:])
    assert event["code"] == "stream_stopped"
    assert q.replay.persistence.result() is False


@pytest.mark.asyncio
async def test_a_stop_while_a_stale_session_is_rebuilt_is_taken_at_the_retry(queue):
    """Rebuilding the session is a second connect, and a stop can land in it.

    The prompt that was live died with the session it ran on, so for that window
    the run is not live either: a stop there is left on the replay, and the retry
    has to take it rather than prompt the agent for a turn the user stopped.
    """
    chat_id, q = queue
    prompted: list[str] = []

    def on_create():
        assert q.replay.producer_started is False
        q.replay.stop_requested = "Stream stopped by user"

    chunks, db = await _run_turn(
        chat_id,
        [],
        [{"stopReason": "error"}, {"stopReason": "end_turn"}],
        replay=q.replay,
        restored=True,
        on_create=on_create,
        prompted=prompted,
    )

    # The first prompt ran; the retry never did.
    assert len(prompted) == 1
    event = json.loads(chunks[-1][6:])
    assert event["type"] == "RUN_ERROR"
    assert event["code"] == "stream_stopped"
    assert q.replay.stop_requested is None
    assert q.replay.persistence.result() is True
