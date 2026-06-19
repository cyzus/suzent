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
    _build_file_mention_context,
    _rebuild_display_messages,
    _strip_attachment_annotations,
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


def test_rebuild_display_messages_marks_denied_tool_return_as_error():
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="bash_execute",
                    args={"content": "python --version"},
                    tool_call_id="tool-denied",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="bash_execute",
                    tool_call_id="tool-denied",
                    content="The tool call was denied.",
                )
            ]
        ),
    ]

    display = _rebuild_display_messages(messages)

    assistant = display[0]
    assert assistant["parts"][0]["state"] == "error"
    assert assistant["parts"][0]["output"] == "The tool call was denied."


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


def test_append_command_messages_adds_user_and_notice_entries():
    existing = [{"role": "assistant", "content": "old"}]
    updated = _append_command_messages(existing, "/compact", "Compaction done")

    assert len(updated) == 3
    assert updated[-2] == {"role": "user", "content": "/compact"}
    assert updated[-1] == {"role": "notice", "content": "Compaction done"}


def test_append_command_messages_skips_empty_assistant_payload():
    updated = _append_command_messages([], "/somecmd", "")

    assert len(updated) == 1
    assert updated[0] == {"role": "user", "content": "/somecmd"}


def test_build_file_mention_context_skips_malformed_entries():
    context = _build_file_mention_context(
        [
            {"path": "/mnt/project/notes.md", "type": "file"},
            {"path": "/mnt/project/docs", "type": "directory"},
            {"path": None},
            {"path": "/mnt/project/bad]\ninject.md"},
            {"path": "relative.md"},
            123,
        ]
    )

    assert "[User referenced file: /mnt/project/notes.md]" in context
    assert "[User referenced directory: /mnt/project/docs]" in context
    assert "inject" not in context
    assert "relative.md" not in context


def test_strip_attachment_annotations_removes_file_reference_annotations():
    text = (
        "summarize this\n"
        "[User referenced file: /mnt/project/notes.md]\n"
        "[User referenced directory: /mnt/project/docs]"
    )

    assert _strip_attachment_annotations(text) == "summarize this"
