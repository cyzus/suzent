"""A slash command turn is stoppable like any other.

The command answers the turn itself, so the agent never runs and nothing
installs a cancellation control. A stop accepted for that run would otherwise
sit unread on the replay while a long command -- /compact, anything that
reaches a remote node -- ran to the end, and the client would have been told
the stop was applied.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from suzent.core.chat_processor import ChatProcessor
from suzent.core.stream_registry import producing_run, register_background_stream
from suzent.core import stream_registry


@pytest.fixture(autouse=True)
def clean_registry():
    stream_registry.background_queues.clear()
    yield
    stream_registry.background_queues.clear()


def _events(chunks):
    out = []
    for chunk in chunks:
        payload = chunk[6:].strip() if chunk.startswith("data: ") else ""
        if payload and payload != "[DONE]":
            out.append(json.loads(payload))
    return out


class _Agent:
    _model_id = "model-test"
    _tool_names: list[str] = []
    _last_messages: list = []


async def _run_command_turn(monkeypatch, stop_before=None, stop_during=None):
    queue = register_background_stream("chat-cmd")
    if stop_before:
        queue.replay.stop_requested = stop_before
    ran: list[str] = []

    async def dispatch(ctx, message):
        ran.append(message)
        if stop_during:
            queue.replay.stop_requested = stop_during
        return "compacted"

    async def get_agent(config):
        return _Agent()

    db = MagicMock()
    db.get_chat.return_value = None

    monkeypatch.setattr(
        "suzent.core.commands.dispatch", AsyncMock(side_effect=dispatch)
    )
    monkeypatch.setattr("suzent.core.chat_processor.get_or_create_agent", get_agent)
    monkeypatch.setattr(
        "suzent.core.chat_processor.build_agent_deps",
        lambda chat_id, user_id, config: SimpleNamespace(
            last_messages=None,
            cancel_event=None,
            is_suspended=False,
            inline_a2ui_surfaces={},
        ),
    )
    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: db)

    with producing_run(queue.replay):
        chunks = [
            chunk
            async for chunk in ChatProcessor().process_turn(
                message_content="/compact", chat_id="chat-cmd", user_id="u"
            )
        ]
    return _events(chunks), ran, queue


@pytest.mark.asyncio
async def test_a_stop_accepted_before_the_command_runs_keeps_it_from_running(
    monkeypatch,
):
    events, ran, queue = await _run_command_turn(
        monkeypatch, stop_before="Stream stopped by user"
    )

    assert ran == []
    stops = [e for e in events if e.get("code") == "stream_stopped"]
    assert stops and stops[0]["message"] == "Stream stopped by user"
    # Taken once: the mark does not outlive the turn that answered it.
    assert queue.replay.stop_requested is None


@pytest.mark.asyncio
async def test_a_stop_accepted_while_the_command_ran_still_gets_its_ending(monkeypatch):
    """Nothing can call the work back, but the client is owed the ending."""
    events, ran, queue = await _run_command_turn(
        monkeypatch, stop_during="Stream stopped by user"
    )

    assert ran == ["/compact"]
    assert any(e.get("code") == "stream_stopped" for e in events)
    assert queue.replay.stop_requested is None


@pytest.mark.asyncio
async def test_an_ordinary_command_turn_is_not_tagged_as_stopped(monkeypatch):
    events, ran, _ = await _run_command_turn(monkeypatch)

    assert ran == ["/compact"]
    assert not any(e.get("code") == "stream_stopped" for e in events)
    assert any("compacted" in str(e.get("delta") or "") for e in events)
