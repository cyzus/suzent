"""A message a busy chat takes in mid-turn is shown where it landed.

Another agent's message reaches a running chat by injection rather than a new
turn. The run absorbed it into its history, but the chat showed nothing of it
until the turn ended.
"""

import json
from types import SimpleNamespace

from ag_ui.core import CustomEvent
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.test import TestModel

from suzent.core.agent_deps import AgentDeps
from suzent.core.system_reminder import wrap_in_system_reminder
from suzent.streaming import (
    _DraftDisplayAccumulator,
    _incoming_message_texts,
    stream_agent_responses,
)

REQUEST = "[Agent message from SUZENT (focal-suzent)]\nAim it at the GitHub page."


def _absorbed(*contents: str) -> SimpleNamespace:
    return SimpleNamespace(
        enqueue_id="enq-1",
        messages=(
            ModelRequest(
                parts=[UserPromptPart(content=content) for content in contents]
            ),
        ),
    )


def test_the_shown_text_is_read_from_the_absorbed_message() -> None:
    event = _absorbed(wrap_in_system_reminder(REQUEST, display_trigger=REQUEST))

    assert _incoming_message_texts(event) == [REQUEST]


def test_a_message_with_nothing_to_show_stays_hidden() -> None:
    event = _absorbed(wrap_in_system_reminder("internal note only"))

    assert _incoming_message_texts(event) == []


def test_the_saved_draft_keeps_it_in_order() -> None:
    draft = _DraftDisplayAccumulator("chat-1", "run-1")
    draft.parts.append({"type": "text", "text": "Working on the page."})

    draft.apply(CustomEvent(name="incoming_message", value={"content": REQUEST}))

    assert draft.parts[-1] == {"type": "incoming-message", "text": REQUEST}
    assert draft.dirty


def test_a_trigger_already_in_the_display_log_stays_out_of_the_draft() -> None:
    draft = _DraftDisplayAccumulator("chat-1", "run-1")

    draft.apply(
        CustomEvent(
            name="incoming_message", value={"content": REQUEST, "persisted": True}
        )
    )

    assert draft.parts == []
    assert not draft.dirty


async def test_a_presaved_trigger_is_streamed_before_the_reply() -> None:
    agent = Agent(TestModel(custom_output_text="On it."))
    events = []
    async for chunk in stream_agent_responses(
        agent, "go", deps=AgentDeps(), presaved_triggers=[REQUEST]
    ):
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))

    kinds = [event["type"] for event in events]
    incoming = [
        event
        for event in events
        if event["type"] == "CUSTOM" and event["name"] == "incoming_message"
    ]
    assert [event["value"] for event in incoming] == [
        {"content": REQUEST, "persisted": True}
    ]
    assert events.index(incoming[0]) < kinds.index("TEXT_MESSAGE_CONTENT")
