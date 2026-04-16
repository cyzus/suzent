from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

from suzent.core.chat_processor import _collect_unprocessed_tool_call_ids


def test_collect_unprocessed_tool_call_ids_returns_pending_calls() -> None:
    history = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="bash_execute",
                    tool_call_id="call-1",
                    args={"command": "pwd"},
                ),
                ToolCallPart(
                    tool_name="bash_execute",
                    tool_call_id="call-2",
                    args={"command": "ls"},
                ),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="bash_execute",
                    tool_call_id="call-1",
                    content="ok",
                )
            ]
        ),
    ]

    pending = _collect_unprocessed_tool_call_ids(history)

    assert pending == {"call-2"}


def test_collect_unprocessed_tool_call_ids_empty_when_all_answered() -> None:
    history = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="bash_execute",
                    tool_call_id="call-1",
                    args={"command": "pwd"},
                ),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="bash_execute",
                    tool_call_id="call-1",
                    content="ok",
                )
            ]
        ),
    ]

    pending = _collect_unprocessed_tool_call_ids(history)

    assert pending == set()
