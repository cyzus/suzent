"""How a turn reports agent-side failures and recovers from a stale session."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suzent.acp.runtime import stream_acp_turn


def _events(chunks):
    out = []
    for chunk in chunks:
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
            out.append(json.loads(chunk[6:].strip()))
    return out


def _managed(session_id="s-1", *, restored=False):
    managed = MagicMock()
    managed.agent_id = "claude-code"
    managed.session_id = session_id
    managed.cwd = "/tmp"
    managed.resumed = True
    managed.restored = restored
    managed.updates = asyncio.Queue()
    return managed


def _turn_error(text="claude cli error:"):
    return {
        "sessionId": "s-1",
        "status": "turn_error",
        "phase": "error",
        "message": text,
        "update": {"sessionUpdate": "agent_thought_chunk"},
    }


def _text_chunk(text):
    return {
        "sessionId": "s-1",
        "update": {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": text},
        },
    }


async def _run(managed_sequence, prompt_results, *, config=None):
    """Drive stream_acp_turn with scripted sessions and prompt outcomes."""
    sessions = list(managed_sequence)
    results = list(prompt_results)

    def attach(managed):
        async def prompt(session_id, message):
            updates, result = results.pop(0)
            for item in updates:
                managed.updates.put_nowait(item)
            return result

        managed.client.prompt = prompt
        return managed

    for item in sessions:
        attach(item)

    with (
        patch("suzent.acp.runtime.get_database") as get_db,
        patch("suzent.acp.runtime.get_acp_manager") as get_manager,
    ):
        chat = MagicMock()
        chat.config = config or {
            "runtime": "acp",
            "acp_agent_id": "claude-code",
            "acp_session_id": "s-1",
        }
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        get_db.return_value = db

        manager = AsyncMock()
        manager.ensure.return_value = sessions[0]
        manager.create.side_effect = lambda *a, **k: sessions[1]
        get_manager.return_value = manager

        events = _events([c async for c in stream_acp_turn("chat-1", "hi")])
        return events, manager, db


@pytest.mark.asyncio
async def test_agent_error_is_reported_instead_of_no_output():
    """stopReason=error must surface the agent's reason, not a generic message."""
    events, _, _ = await _run(
        [_managed()],
        [([_turn_error("claude cli error: quota exhausted")], {"stopReason": "error"})],
    )
    errors = [e for e in events if e["type"] == "RUN_ERROR"]
    assert len(errors) == 1
    assert "quota exhausted" in errors[0]["message"]
    assert "produced no output text" not in errors[0]["message"]


@pytest.mark.asyncio
async def test_unhelpful_stop_reason_is_still_named():
    events, _, _ = await _run([_managed()], [([], {"stopReason": "refusal"})])
    error = next(e for e in events if e["type"] == "RUN_ERROR")
    assert "refusal" in error["message"]


@pytest.mark.asyncio
async def test_plain_empty_turn_keeps_the_generic_message():
    events, _, _ = await _run([_managed()], [([], {"stopReason": "end_turn"})])
    error = next(e for e in events if e["type"] == "RUN_ERROR")
    assert error["message"] == "ACP agent produced no output text"


@pytest.mark.asyncio
async def test_stale_restored_session_recovers_on_a_fresh_one():
    """An agent that accepts a dead session id must not brick the chat."""
    first = _managed("s-1", restored=True)
    second = _managed("s-2")
    events, manager, db = await _run(
        [first, second],
        [
            ([_turn_error()], {"stopReason": "error"}),
            ([_text_chunk("THREE")], {"stopReason": "end_turn"}),
        ],
    )

    assert manager.create.await_count == 1
    resets = [e for e in events if e.get("name") == "acp.session_reset"]
    assert [r["value"]["reason"] for r in resets] == ["stale_session"]
    assert resets[0]["value"]["requestedSessionId"] == "s-1"
    assert resets[0]["value"]["sessionId"] == "s-2"

    deltas = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert deltas == "THREE"
    assert not [e for e in events if e["type"] == "RUN_ERROR"]
    # The working session id must replace the stale one.
    assert any(
        call.args[1].get("acp_session_id") == "s-2"
        for call in db.merge_chat_config.call_args_list
    )


@pytest.mark.asyncio
async def test_a_live_session_failure_does_not_start_a_new_session():
    """Only a freshly restored session earns a retry; a proven one just errors."""
    events, manager, _ = await _run(
        [_managed("s-1", restored=False)],
        [([_turn_error("transient")], {"stopReason": "error"})],
    )
    assert manager.create.await_count == 0
    assert any(e["type"] == "RUN_ERROR" for e in events)
    assert not [e for e in events if e.get("name") == "acp.session_reset"]


@pytest.mark.asyncio
async def test_successful_turn_clears_the_restored_flag():
    managed = _managed("s-1", restored=True)
    await _run([managed], [([_text_chunk("ok")], {"stopReason": "end_turn"})])
    assert managed.restored is False
