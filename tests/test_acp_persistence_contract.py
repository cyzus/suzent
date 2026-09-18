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

from suzent.acp.runtime import stream_acp_turn
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


async def _run_turn(chat_id, updates, result, *, append_result=True, replay=None):
    managed = _managed()

    async def prompt(session_id, message):
        for item in updates:
            managed.updates.put_nowait(item)
        return result

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
        manager.ensure.return_value = managed
        get_manager.return_value = manager

        chunks = [c async for c in stream_acp_turn(chat_id, "hi", replay=replay)]
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
