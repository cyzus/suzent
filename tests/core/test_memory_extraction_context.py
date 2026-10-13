"""What a turn leaves in the transcript, which memory extraction reads.

The extractor should see the user's words and this turn's work, nothing else:
the hidden reminder carries recalled memories (re-extracting them is a feedback
loop), and the snapshot post-processing is handed is the whole chat history, whose
earlier tool calls belong to earlier turns.
"""

import json

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core.chat_processor import (
    ChatProcessor,
    _answered_tool_call_ids,
    _cancel_unprocessed_tool_calls,
    _extract_tool_calls,
)
from suzent.core.system_reminder import wrap_in_system_reminder

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


def test_failed_validation_counts_as_answered():
    history = _history() + [
        _call("bad", "read_file"),
        ModelRequest(
            parts=[
                RetryPromptPart(
                    content="missing path", tool_name="read_file", tool_call_id="bad"
                )
            ]
        ),
    ]

    assert "bad" in _answered_tool_call_ids(history)


def test_abandoned_call_is_not_reported_on_the_next_turn():
    """An interrupted run's call is cancelled before the snapshot, not after."""
    history, _ = _cancel_unprocessed_tool_calls(
        _history() + [_call("abandoned", "bash")], "interrupted"
    )

    assert (
        _extract_tool_calls(history, exclude_ids=_answered_tool_call_ids(history)) == []
    )


async def test_transcript_turn_is_the_users_words_and_this_turns_work(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("suzent.session.transcript.DATA_DIR", tmp_path)
    history = _history()
    prior = _answered_tool_call_ids(history)
    history += [_call("new", "read_file"), _return("new", "read_file", "contents")]

    await ChatProcessor.__new__(ChatProcessor)._write_transcript(
        "c1",
        "I moved to Lisbon" + wrap_in_system_reminder(RECALLED),
        "Noted.",
        history,
        prior,
    )

    lines = (tmp_path / "transcripts" / "c1.jsonl").read_text().splitlines()
    user, assistant = (json.loads(line) for line in lines)
    assert user["content"] == "I moved to Lisbon"
    assert assistant["actions"] == [
        {"tool": "read_file", "args": {"q": "read_file"}, "output": "contents"}
    ]
