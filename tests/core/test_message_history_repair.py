from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core.message_history import (
    is_tool_history_protocol_error,
    safe_tool_history_tail_start,
    strip_tool_interactions,
)


def _tool_call(tool_call_id: str) -> ToolCallPart:
    return ToolCallPart(
        tool_name="bash_execute",
        tool_call_id=tool_call_id,
        args={"command": "pwd"},
    )


def _tool_result(tool_call_id: str) -> ToolReturnPart:
    return ToolReturnPart(
        tool_name="bash_execute",
        tool_call_id=tool_call_id,
        content="ok",
    )


def test_safe_tail_moves_before_matching_tool_call() -> None:
    history = [
        ModelRequest(parts=[UserPromptPart(content="old")]),
        ModelResponse(parts=[TextPart(content="old answer")]),
        ModelResponse(parts=[_tool_call("call-1")]),
        ModelRequest(parts=[_tool_result("call-1")]),
        ModelRequest(parts=[UserPromptPart(content="new")]),
    ]

    assert safe_tool_history_tail_start(history, 3) == 2


def test_recognizes_repairable_openai_compatible_error() -> None:
    class ProtocolError(Exception):
        status_code = 400

    protocol_error = ProtocolError(
        "Messages with role 'tool' must be a response to a preceding "
        "message with 'tool_calls'"
    )

    assert is_tool_history_protocol_error(protocol_error)
    assert not is_tool_history_protocol_error(ValueError("unrelated"))


def test_last_resort_strip_preserves_text_and_user_messages() -> None:
    history = [
        ModelResponse(
            parts=[
                TextPart(content="I will inspect it."),
                _tool_call("call-1"),
            ]
        ),
        ModelRequest(
            parts=[
                _tool_result("call-1"),
                UserPromptPart(content="continue"),
            ]
        ),
    ]

    stripped, removed = strip_tool_interactions(history)

    assert removed == 2
    assert isinstance(stripped[0].parts[0], TextPart)
    assert isinstance(stripped[1].parts[0], UserPromptPart)
