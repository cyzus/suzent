import json

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
    _preserve_citation_sources,
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


def test_preserve_citation_sources_attaches_turn_sources_to_rebuilt_message():
    # Both sources were registered in turn 0; only t0_src_1 is cited inline. Both
    # must survive onto the turn-0 assistant message \u2014 registration, not inline
    # citation, decides persistence (mirrors the streaming path).
    rebuilt = [
        {"role": "user", "content": "what happened?"},
        {
            "role": "assistant",
            "content": "Gold rose\ue200cite\ue202t0_src_1\ue201.",
            "parts": [
                {"type": "text", "text": "Gold rose\ue200cite\ue202t0_src_1\ue201."}
            ],
        },
    ]
    existing = [
        {
            "role": "assistant",
            "content": "draft",
            "parts": [
                {
                    "type": "citation-sources",
                    "citationSources": [
                        {
                            "id": "t0_src_1",
                            "type": "search",
                            "title": "Reuters",
                            "url": "https://reuters.com/a",
                        },
                        {
                            "id": "t0_src_2",
                            "type": "search",
                            "title": "Uncited",
                            "url": "https://example.com/uncited",
                        },
                    ],
                }
            ],
        }
    ]

    updated = _preserve_citation_sources(rebuilt, existing)

    assert updated[1]["parts"][1] == {
        "type": "citation-sources",
        "citationSources": [
            {
                "id": "t0_src_1",
                "type": "search",
                "title": "Reuters",
                "url": "https://reuters.com/a",
            },
            {
                "id": "t0_src_2",
                "type": "search",
                "title": "Uncited",
                "url": "https://example.com/uncited",
            },
        ],
    }


def test_preserve_citation_sources_associates_sources_by_turn():
    # Two turns, each with one source. Each source must land on its own turn's
    # assistant message \u2014 not bleed across turns and not require an inline marker.
    rebuilt = [
        {"role": "user", "content": "q1"},
        {
            "role": "assistant",
            "content": "answer one",
            "parts": [{"type": "text", "text": "answer one"}],
        },
        {"role": "user", "content": "q2"},
        {
            "role": "assistant",
            "content": "answer two",
            "parts": [{"type": "text", "text": "answer two"}],
        },
    ]
    existing = [
        {
            "role": "assistant",
            "content": "draft",
            "parts": [
                {
                    "type": "citation-sources",
                    "citationSources": [
                        {"id": "t0_src_1", "type": "search", "title": "First"},
                        {"id": "t1_src_1", "type": "search", "title": "Second"},
                    ],
                }
            ],
        }
    ]

    updated = _preserve_citation_sources(rebuilt, existing)

    assert updated[1]["parts"][1] == {
        "type": "citation-sources",
        "citationSources": [{"id": "t0_src_1", "type": "search", "title": "First"}],
    }
    assert updated[3]["parts"][1] == {
        "type": "citation-sources",
        "citationSources": [{"id": "t1_src_1", "type": "search", "title": "Second"}],
    }


def test_preserve_citation_sources_recovers_sources_from_tool_results():
    tool_content = {
        "success": True,
        "message": json.dumps(
            {
                "source": "DDGS (news)",
                "results": [
                    {
                        "title": "Stock Market Today",
                        "url": "https://example.com/markets",
                        "description": "Nasdaq and S&P 500 moved lower.",
                        "source_id": "t0_src_14",
                    },
                    {
                        "title": "Unused",
                        "url": "https://example.com/unused",
                        "description": "Unused source.",
                        "source_id": "t0_src_15",
                    },
                ],
            }
        ),
    }
    rebuilt = [
        {"role": "tool", "content": json.dumps(tool_content)},
        {
            "role": "assistant",
            "content": "Tech stocks fell \ue200cite\ue202t0_src_14\ue201.",
            "parts": [
                {
                    "type": "text",
                    "text": "Tech stocks fell \ue200cite\ue202t0_src_14\ue201.",
                }
            ],
        },
    ]

    updated = _preserve_citation_sources(rebuilt, [])

    # Both sources from the turn-0 tool result are recovered, including the one
    # the model never cited inline (t0_src_15).
    assert updated[1]["parts"][1]["type"] == "citation-sources"
    assert updated[1]["parts"][1]["citationSources"] == [
        {
            "id": "t0_src_14",
            "type": "search",
            "title": "Stock Market Today",
            "url": "https://example.com/markets",
            "snippet": "Nasdaq and S&P 500 moved lower.",
            "favicon": "https://www.google.com/s2/favicons?domain=example.com&sz=32",
        },
        {
            "id": "t0_src_15",
            "type": "search",
            "title": "Unused",
            "url": "https://example.com/unused",
            "snippet": "Unused source.",
            "favicon": "https://www.google.com/s2/favicons?domain=example.com&sz=32",
        },
    ]


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
