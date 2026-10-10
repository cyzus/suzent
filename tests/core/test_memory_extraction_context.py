"""What the memory extractor is shown for a turn.

The extractor should see the user's words and this turn's work, nothing else:
the hidden reminder carries recalled memories (re-extracting them is a feedback
loop), and the snapshot it is handed is the whole chat history, whose earlier tool
calls were already extracted on their own turns.
"""

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core import chat_processor
from suzent.core.chat_processor import (
    ChatProcessor,
    _answered_tool_call_ids,
    _extract_tool_calls,
)
from suzent.core.context_compressor import ContextCompressor
from suzent.core.system_reminder import wrap_in_system_reminder
from suzent.memory import memory_context

RECALLED = "Relevant memories: Lives in Berlin"


def _call(call_id: str, tool: str) -> ModelResponse:
    return ModelResponse(
        parts=[ToolCallPart(tool_name=tool, args={"q": tool}, tool_call_id=call_id)]
    )


def _return(call_id: str, tool: str, output: str) -> ModelRequest:
    return ModelRequest(
        parts=[ToolReturnPart(tool_name=tool, content=output, tool_call_id=call_id)]
    )


def _history() -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content="earlier question")]),
        _call("old", "web_search"),
        _return("old", "web_search", "old result"),
        ModelResponse(parts=[TextPart(content="earlier answer")]),
    ]


class _RecordingMemory:
    def __init__(self) -> None:
        self.turns = []

    async def process_conversation_turn_for_memories(
        self, conversation_turn, chat_id, user_id
    ):
        self.turns.append(conversation_turn)
        return SimpleNamespace(extracted_facts=[])


@pytest.fixture
def memory(monkeypatch):
    recorder = _RecordingMemory()
    monkeypatch.setattr(chat_processor.CONFIG, "memory_enabled", True)
    monkeypatch.setattr(chat_processor, "get_memory_manager", lambda: recorder)
    monkeypatch.setattr("suzent.memory.lifecycle.get_memory_manager", lambda: recorder)
    return recorder


def test_previously_answered_calls_are_excluded():
    history = _history()
    prior = _answered_tool_call_ids(history)
    history += [_call("new", "read_file"), _return("new", "read_file", "contents")]

    actions = _extract_tool_calls(history, exclude_ids=prior)

    assert [(a.tool, a.output) for a in actions] == [("read_file", "contents")]


def test_call_awaiting_approval_counts_as_this_turn():
    """A resumed approval was made last run but only answered now."""
    history = _history() + [_call("pending", "bash")]
    prior = _answered_tool_call_ids(history)
    history.append(_return("pending", "bash", "ok"))

    actions = _extract_tool_calls(history, exclude_ids=prior)

    assert [a.tool for a in actions] == ["bash"]


async def test_turn_excludes_reminder_and_earlier_calls(memory, monkeypatch):
    processor = ChatProcessor.__new__(ChatProcessor)
    monkeypatch.setattr(processor, "_is_system_chat", lambda chat_id: False)
    history = _history()
    prior = _answered_tool_call_ids(history)
    history += [_call("new", "read_file"), _return("new", "read_file", "contents")]

    await processor._extract_memories(
        chat_id="c1",
        user_id="u1",
        user_content="I moved to Lisbon" + wrap_in_system_reminder(RECALLED),
        agent_content="Noted.",
        messages=history,
        prior_tool_call_ids=prior,
    )

    (turn,) = memory.turns
    assert turn.user_message.content == "I moved to Lisbon"
    assert [a.tool for a in turn.agent_actions] == ["read_file"]


async def test_pre_compaction_flush_takes_only_user_words(memory):
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="You are Suzent."),
                UserPromptPart(
                    content="I moved to Lisbon" + wrap_in_system_reminder(RECALLED)
                ),
            ]
        ),
        _call("c1", "web_search"),
        _return("c1", "web_search", "search result"),
        ModelResponse(parts=[TextPart(content="Noted.")]),
    ]
    compressor = SimpleNamespace(chat_id="c1", user_id="u1")

    await ContextCompressor._pre_compaction_flush(compressor, messages)

    (turn,) = memory.turns
    assert turn.user_message.content == "I moved to Lisbon"
    assert [(a.tool, a.output) for a in turn.agent_actions] == [
        ("web_search", "search result")
    ]


def test_prompt_carries_current_date():
    prompt = memory_context.format_fact_extraction_user_prompt(
        "a turn", current_date="2026-10-10 (Saturday, UTC+0800)"
    )

    assert "Current date: 2026-10-10 (Saturday, UTC+0800)" in prompt
    assert "Current date" not in memory_context.format_fact_extraction_user_prompt(
        "a turn"
    )
