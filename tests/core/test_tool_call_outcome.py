"""A failed tool call is reported as failed, live and after a reload.

The AG-UI tool result carries only text, so a call rejected for bad
arguments, or one that raised, used to look exactly like a success: the UI
drew a checkmark over "2 validation errors".
"""

from ag_ui.core import CustomEvent, RunAgentInput
from pydantic_ai.messages import (
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core.chat_processor import _rebuild_display_messages
from suzent.streaming import (
    _DraftDisplayAccumulator,
    _SuzentAGUIEventStream,
    tool_call_outcome,
)


def _validation_retry(tool_call_id: str = "call-1") -> RetryPromptPart:
    return RetryPromptPart(
        tool_name="run_command",
        tool_call_id=tool_call_id,
        content=[
            {
                "type": "missing",
                "loc": ("content",),
                "msg": "Field required",
                "input": {},
            }
        ],
    )


def test_outcome_of_each_kind_of_result():
    assert tool_call_outcome(_validation_retry()) == "failed"
    assert (
        tool_call_outcome(
            ToolReturnPart(
                tool_name="t", tool_call_id="c", content="boom", outcome="failed"
            )
        )
        == "failed"
    )
    assert (
        tool_call_outcome(
            ToolReturnPart(
                tool_name="t", tool_call_id="c", content="", outcome="interrupted"
            )
        )
        == "interrupted"
    )
    assert (
        tool_call_outcome(ToolReturnPart(tool_name="t", tool_call_id="c", content="ok"))
        is None
    )
    # Denials have their own approval events.
    assert (
        tool_call_outcome(
            ToolReturnPart(
                tool_name="t", tool_call_id="c", content="no", outcome="denied"
            )
        )
        is None
    )
    # A retry prompt not tied to a tool is the model's output being rejected.
    assert tool_call_outcome(RetryPromptPart(content="try again")) is None


async def _stream_events(event):
    stream = _SuzentAGUIEventStream(
        RunAgentInput(
            thread_id="t",
            run_id="r",
            messages=[],
            state=None,
            tools=[],
            context=[],
            forwarded_props=None,
        )
    )
    return [e async for e in stream.handle_function_tool_result(event)]


async def test_a_rejected_call_streams_its_outcome_after_the_result():
    events = await _stream_events(FunctionToolResultEvent(part=_validation_retry()))

    assert [type(e).__name__ for e in events] == ["ToolCallResultEvent", "CustomEvent"]
    assert events[1].name == "tool_call_outcome"
    assert events[1].value == {"toolCallId": "call-1", "outcome": "failed"}


async def test_a_successful_call_streams_no_outcome():
    events = await _stream_events(
        FunctionToolResultEvent(
            part=ToolReturnPart(
                tool_name="run_command", tool_call_id="call-1", content="ok"
            )
        )
    )
    assert not any(isinstance(e, CustomEvent) for e in events)


def test_the_draft_records_the_outcome():
    draft = _DraftDisplayAccumulator(chat_id=None, run_id="r")
    draft.apply(
        CustomEvent(
            name="tool_call_outcome",
            value={"toolCallId": "call-1", "outcome": "failed"},
        )
    )
    assert draft.parts[0]["outcome"] == "failed"


def test_a_rejected_call_rebuilds_as_a_failed_finished_call():
    history = [
        ModelRequest(parts=[UserPromptPart(content="go")]),
        ModelResponse(
            parts=[
                ToolCallPart(tool_name="run_command", tool_call_id="call-1", args={})
            ]
        ),
        ModelRequest(parts=[_validation_retry()]),
    ]

    tool_parts = [
        part
        for message in _rebuild_display_messages(history)
        for part in message.get("parts") or []
        if part.get("type") == "tool"
    ]

    assert len(tool_parts) == 1
    assert tool_parts[0]["outcome"] == "failed"
    assert tool_parts[0]["state"] == "completed"
    assert "Field required" in tool_parts[0]["output"]
