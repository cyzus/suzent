"""A run is live for a stop only once its prompt has reached the agent.

`/chat/stop` answers for an ACP run by cancelling the chat's session, which
only stops this run if the session is actually running this run's prompt.
Scheduling the prompt is not sending it: the request is written by a task, so
between scheduling and the first byte the session is still idle and a
`session/cancel` sent then is answered by a session with nothing to cancel --
after which the prompt goes out and the stopped turn runs on.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suzent.acp.runtime import stream_acp_turn
from suzent.core.stream_registry import background_queues, register_background_stream


@pytest.fixture
def queue():
    chat_id = "chat-stop-liveness"
    q = register_background_stream(chat_id)
    try:
        yield chat_id, q
    finally:
        background_queues.pop(chat_id, None)


async def _run(chat_id, replay, prompt_impl):
    managed = MagicMock()
    managed.chat_id = chat_id
    managed.agent_id = "claude-code"
    managed.session_id = "s-1"
    managed.cwd = "/tmp"
    managed.restored = False
    managed.updates = asyncio.Queue()
    managed.client.prompt = prompt_impl

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
        db.append_chat_message.return_value = True
        get_db.return_value = db

        manager = AsyncMock()
        manager.ensure.return_value = managed
        manager.create.return_value = managed
        get_manager.return_value = manager

        chunks = [c async for c in stream_acp_turn(chat_id, "hi", replay=replay)]
        return chunks, manager


@pytest.mark.asyncio
async def test_a_run_is_not_live_until_its_prompt_has_been_sent(queue):
    chat_id, q = queue
    seen: list[bool] = []

    async def prompt(session_id, message, on_sent=None):
        # Standing in for everything `client.request` does before the write:
        # the request is scheduled, so a stop arriving now would find the
        # session idle.
        await asyncio.sleep(0)
        seen.append(q.replay.producer_started)
        if on_sent is not None:
            on_sent()
        # The real client awaits its reply from here, which is where the turn
        # gets the loop back and takes the run live.
        for _ in range(20):
            if q.replay.producer_started:
                break
            await asyncio.sleep(0)
        seen.append(q.replay.producer_started)
        return {"stopReason": "end_turn", "text": "hello"}

    await _run(chat_id, q.replay, prompt)

    assert seen == [False, True]


@pytest.mark.asyncio
async def test_a_stop_accepted_while_the_prompt_was_in_flight_is_delivered(queue):
    """The route left it on the replay because nothing could carry it out yet.

    Dropping it here would be the worst of both: the client was told the stop
    was accepted, and the agent was never told anything.
    """
    chat_id, q = queue

    async def prompt(session_id, message, on_sent=None):
        # The stop lands while the prompt is still on its way: the run is not
        # live, so /chat/stop leaves it on the replay rather than cancelling a
        # session that is running nothing.
        assert q.replay.producer_started is False
        q.replay.stop_requested = "Stream stopped by user"
        if on_sent is not None:
            on_sent()
        return {"stopReason": "cancelled"}

    chunks, manager = await _run(chat_id, q.replay, prompt)

    manager.cancel.assert_awaited_once_with(chat_id)
    # Taken once, and the turn ends as the stop the client asked for.
    assert q.replay.stop_requested is None
    assert '"code":"stream_stopped"' in "".join(chunks)


@pytest.mark.asyncio
async def test_a_prompt_that_never_reaches_the_agent_leaves_nothing_behind(queue):
    """The waiter for a signal that never comes is the turn's to clean up.

    A dead process raises before the request is written, so the race is won by
    the failure. Dropping the loser instead of cancelling it holds a task and
    its event for the life of the process -- one pair per failed connection.
    """
    chat_id, q = queue

    async def prompt(session_id, message, on_sent=None):
        raise RuntimeError("ACP process is not running")

    before = len(asyncio.all_tasks())
    await _run(chat_id, q.replay, prompt)
    await asyncio.sleep(0)

    assert len(asyncio.all_tasks()) <= before
