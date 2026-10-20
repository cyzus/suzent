"""A message a busy chat takes in mid-turn is shown where it landed.

Another agent's message reaches a running chat by injection rather than a new
turn. The run absorbed it into its history, but the chat showed nothing of it
until the turn ended.
"""

from types import SimpleNamespace

from ag_ui.core import CustomEvent
from pydantic_ai.messages import ModelRequest, UserPromptPart

from suzent.core.system_reminder import wrap_in_system_reminder
from suzent.streaming import _DraftDisplayAccumulator, _incoming_message_texts

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
