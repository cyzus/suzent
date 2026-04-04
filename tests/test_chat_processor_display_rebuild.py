from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core.chat_processor import (
    _append_command_messages,
    _append_inline_a2ui_surfaces,
    _rebuild_display_messages,
)


def test_rebuild_display_messages_preserves_reasoning():
    messages = [
        ModelRequest(parts=[UserPromptPart(content="hello")]),
        ModelResponse(
            parts=[
                ThinkingPart(content="considering the options"),
                TextPart(content="final answer"),
                ToolCallPart(
                    tool_name="render_ui",
                    args={"surface_id": "results"},
                    tool_call_id="tool-1",
                ),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="render_ui",
                    tool_call_id="tool-1",
                    content="Surface rendered",
                )
            ]
        ),
    ]

    display = _rebuild_display_messages(messages)

    assert len(display) == 3
    assistant = display[1]
    assert assistant["role"] == "assistant"
    assert "final answer" in assistant["content"]
    assert 'data-reasoning="true"' in assistant["content"]


def test_rebuild_display_messages_preserves_reasoning_order_before_text():
    messages = [
        ModelRequest(parts=[UserPromptPart(content="hello")]),
        ModelResponse(
            parts=[
                ThinkingPart(content="plan first"),
                TextPart(content="then final"),
            ]
        ),
    ]

    display = _rebuild_display_messages(messages)
    assistant = display[1]
    content = assistant["content"]
    assert content.index('data-reasoning="true"') < content.index("then final")


def test_append_inline_a2ui_surfaces_attaches_to_last_assistant_message():
    display = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "final answer"},
    ]

    updated = _append_inline_a2ui_surfaces(
        display,
        {
            "surface-1": {
                "id": "surface-1",
                "title": "Results",
                "component": {"type": "text", "content": "inline"},
                "target": "inline",
            }
        },
    )

    assert updated[1]["role"] == "assistant"
    assert "data-a2ui=" in updated[1]["content"]


def test_append_command_messages_adds_user_and_assistant_entries():
    existing = [{"role": "assistant", "content": "old"}]
    updated = _append_command_messages(existing, "/compact", "Compaction done")

    assert len(updated) == 3
    assert updated[-2] == {"role": "user", "content": "/compact"}
    assert updated[-1] == {"role": "assistant", "content": "Compaction done"}


def test_append_command_messages_skips_empty_assistant_payload():
    updated = _append_command_messages([], "/somecmd", "")

    assert len(updated) == 1
    assert updated[0] == {"role": "user", "content": "/somecmd"}
