"""A turn started by a hidden message shows that message while it runs.

A session SUZENT starts, or one another agent writes to, gets its request as
a hidden reminder. Nothing reached the display log until the turn ended, so
anyone watching saw the reply arrive with no sign of what was asked.
"""

from types import SimpleNamespace

import pytest

import suzent.core.chat_processor as chat_processor
from suzent.core.chat_processor import ChatProcessor


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch):
    presaved: list[tuple[str, list[dict]]] = []
    seen_before_reply: list[list] = []
    announced: list[list[str]] = []

    class FakeAgent:
        _model_id = "model-test"
        _tool_names: list[str] = []
        _last_messages: list = []

    async def get_agent(config):
        return FakeAgent()

    async def stream(*args, **kwargs):
        seen_before_reply.append(list(presaved))
        announced.append(list(kwargs.get("presaved_triggers", ())))
        yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "ok"}\n\n'

    async def no_snapshot(self, *args, **kwargs):
        return None

    async def no_register(coro, task_id=None, description="", allow_overflow=False):
        coro.close()

    async def no_wait(prefix, timeout=None):
        return None

    chat = SimpleNamespace(messages=[], config={}, project_id=None)
    monkeypatch.setattr(chat_processor, "get_or_create_agent", get_agent)
    monkeypatch.setattr(
        chat_processor,
        "build_agent_deps",
        lambda chat_id, user_id, config: SimpleNamespace(
            last_messages=None,
            cancel_event=None,
            is_suspended=False,
            inline_a2ui_surfaces={},
            context_sources={},
        ),
    )
    monkeypatch.setattr(chat_processor, "stream_agent_responses", stream)
    monkeypatch.setattr(ChatProcessor, "_persist_agent_state_snapshot", no_snapshot)
    monkeypatch.setattr(
        "suzent.core.task_registry.register_background_task", no_register
    )
    monkeypatch.setattr(
        "suzent.core.task_registry.wait_for_background_task_prefix", no_wait
    )
    monkeypatch.setattr(
        chat_processor,
        "get_database",
        lambda: SimpleNamespace(
            get_chat=lambda chat_id: chat,
            append_display_rows=lambda chat_id, rows: presaved.append(("", list(rows))),
        ),
    )
    monkeypatch.setattr(
        chat_processor,
        "_presave_turn_rows",
        lambda chat_id, prompt, rows: presaved.append((prompt, list(rows))),
    )

    async def run(**kwargs) -> None:
        async for _ in ChatProcessor().process_turn(
            chat_id="chat-1", user_id="user-1", **kwargs
        ):
            pass

    return run, seen_before_reply, announced


async def test_a_hidden_request_is_on_screen_before_the_reply(turn) -> None:
    run, seen_before_reply, _ = turn

    await run(
        message_content="",
        system_reminders=["[Agent message from SUZENT]\nBuild the landing page"],
    )

    [presaved] = seen_before_reply
    [(prompt, rows)] = presaved
    assert prompt == ""
    assert rows[0]["role"] == "system_triggered"
    assert "Build the landing page" in rows[0]["content"]


async def test_a_typed_message_is_left_to_the_client(turn) -> None:
    run, seen_before_reply, announced = turn

    await run(message_content="hello")

    assert seen_before_reply == [[]]
    assert announced == [[]]


async def test_the_stream_announces_the_row_it_wrote_early(turn) -> None:
    # The client reloads the display log as soon as the stream opens, which is
    # before this row lands, so the stream has to carry it.
    run, seen_before_reply, announced = turn

    await run(
        message_content="",
        system_reminders=["[Agent message from SUZENT]\nBuild the landing page"],
    )

    [[(_, rows)]] = seen_before_reply
    assert announced == [[rows[0]["content"]]]


def test_a_finishing_earlier_turn_cannot_drop_the_early_row(temp_db) -> None:
    chat_id = temp_db.create_chat("Session", {})
    previous_turn = temp_db.commit_snapshot_state(chat_id, b"state")
    row = {
        "role": "system_triggered",
        "content": "[Agent message from SUZENT (focal-suzent)]\nBuild it",
        "trigger_origin": "runtime",
    }

    assert temp_db.append_display_rows(chat_id, [row])
    # The earlier turn's finalizer still holds its revision and would replace
    # the whole display log with its own view, which has no row for this turn.
    finalized = temp_db.finalize_state_if_revision_matches(
        chat_id, previous_turn, b"state", messages=[]
    )

    assert finalized is False
    assert temp_db.get_chat(chat_id).messages == [row]


def test_the_early_row_is_written_once(temp_db) -> None:
    chat_id = temp_db.create_chat("Session", {})
    row = {"role": "system_triggered", "content": "Build it"}

    temp_db.append_display_rows(chat_id, [row])
    temp_db.append_display_rows(chat_id, [row])

    assert temp_db.get_chat(chat_id).messages == [row]
