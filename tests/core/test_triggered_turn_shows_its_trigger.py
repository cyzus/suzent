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

    class FakeAgent:
        _model_id = "model-test"
        _tool_names: list[str] = []
        _last_messages: list = []

    async def get_agent(config):
        return FakeAgent()

    async def stream(*args, **kwargs):
        seen_before_reply.append(list(presaved))
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
        lambda: SimpleNamespace(get_chat=lambda chat_id: chat),
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

    return run, seen_before_reply


async def test_a_hidden_request_is_on_screen_before_the_reply(turn) -> None:
    run, seen_before_reply = turn

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
    run, seen_before_reply = turn

    await run(message_content="hello")

    assert seen_before_reply == [[]]
