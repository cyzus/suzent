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


async def _run_command_turn(
    monkeypatch, stop_before=None, stop_during=None, write_fails=False, wrote=True
):
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
    chat = MagicMock()
    chat.messages = []
    db.get_chat.return_value = chat
    if write_fails:
        db.update_chat.side_effect = RuntimeError("disk full")
    else:
        db.update_chat.return_value = wrote

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
    return _events(chunks), ran, queue, db


@pytest.mark.asyncio
async def test_a_stop_accepted_before_the_command_runs_keeps_it_from_running(
    monkeypatch,
):
    events, ran, queue, db = await _run_command_turn(
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
    events, ran, queue, db = await _run_command_turn(
        monkeypatch, stop_during="Stream stopped by user"
    )

    assert ran == ["/compact"]
    assert any(e.get("code") == "stream_stopped" for e in events)
    assert queue.replay.stop_requested is None


@pytest.mark.asyncio
async def test_an_ordinary_command_turn_is_not_tagged_as_stopped(monkeypatch):
    events, ran, _, db = await _run_command_turn(monkeypatch)

    assert ran == ["/compact"]
    assert not any(e.get("code") == "stream_stopped" for e in events)
    assert any("compacted" in str(e.get("delta") or "") for e in events)


@pytest.mark.asyncio
async def test_a_command_stopped_before_it_ran_still_stores_what_was_shown(monkeypatch):
    """Nothing prewrites a slash command, and this turn ends without the agent.

    The stream tells the client the reload is trustworthy, so the rows it was
    shown -- the command and the notice -- have to be there when it reloads.
    """
    _, ran, _, db = await _run_command_turn(
        monkeypatch, stop_before="Stream stopped by user"
    )

    assert ran == []
    (_, kwargs) = db.update_chat.call_args
    assert [(m["role"], m["content"]) for m in kwargs["messages"]] == [
        ("user", "/compact"),
        ("notice", "⏹ Stopped before the command ran."),
    ]


@pytest.mark.asyncio
async def test_a_command_turn_that_could_not_store_its_rows_says_so(monkeypatch):
    """A failed write must not pass for a good one.

    The client reads STREAM_END{persisted:true} as permission to reload, and on
    a reload after a failed write the command and the notice it was just shown
    are gone. A replay with no persistence future reports true, so this turn has
    to attach its own answer.
    """
    _, ran, queue, db = await _run_command_turn(
        monkeypatch, stop_before="Stream stopped by user", write_fails=True
    )

    assert ran == []
    queue.replay.closed = True
    assert queue.replay.persisted is False


@pytest.mark.asyncio
async def test_a_command_turn_that_stored_its_rows_reports_a_trustworthy_reload(
    monkeypatch,
):
    _, ran, queue, _ = await _run_command_turn(monkeypatch)

    assert ran == ["/compact"]
    queue.replay.closed = True
    assert queue.replay.persisted is True


@pytest.mark.asyncio
async def test_a_command_turn_whose_chat_vanished_mid_write_says_so(monkeypatch):
    """`update_chat` answers False when the chat is gone, without raising.

    The row was looked up and then deleted, so nothing was stored -- and a turn
    that reports that write as good sends the client to a reload that drops the
    command and the notice it was shown.
    """
    _, ran, queue, _ = await _run_command_turn(
        monkeypatch, stop_before="Stream stopped by user", wrote=False
    )

    assert ran == []
    queue.replay.closed = True
    assert queue.replay.persisted is False


@pytest.mark.asyncio
async def test_a_failed_command_write_is_logged_without_the_prompt(monkeypatch):
    """A database error carries its statement's bound parameters.

    Here those are the command the user typed and the whole transcript it was
    appended to, so the log gets the exception's type and nothing else.
    """
    from suzent.core import chat_processor

    written: list[str] = []
    monkeypatch.setattr(
        chat_processor.logger, "debug", lambda msg, *a, **k: written.append(str(msg))
    )

    class _Leaky(RuntimeError):
        def __str__(self):
            return "UPDATE chats SET messages=? -- ['/compact', 'the transcript']"

    db = MagicMock()
    chat = MagicMock()
    chat.messages = []
    db.get_chat.return_value = chat
    db.update_chat.side_effect = _Leaky()
    monkeypatch.setattr(chat_processor, "get_database", lambda: db)

    assert chat_processor._persist_command_pair("chat-cmd", "/compact", "note") is False
    assert written and all("/compact" not in line for line in written)
    assert any("_Leaky" in line for line in written)
