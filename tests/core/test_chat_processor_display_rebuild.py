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
    _agent_history_is_compacted,
    _append_command_messages,
    _append_inline_a2ui_surfaces,
    _build_file_mention_context,
    _merge_rebuilt_after_compaction,
    _preserve_citation_sources,
    _rebuild_display_messages,
    _resolve_response_model,
    _response_provider_matches_run,
    _strip_attachment_annotations,
)
from suzent.core.context_compressor import (
    COMPACTION_SUMMARY_REQUEST_MARKER,
    COMPACTION_SUMMARY_RESPONSE_MARKER,
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


def test_rebuild_stamps_per_response_model_when_switched_mid_chat():
    # User switched from sonnet to opus mid-chat; the run-level model_id is the
    # *current* model (opus). Each assistant message must show the model that
    # actually produced it, not the current one.
    messages = [
        ModelRequest(parts=[UserPromptPart(content="q1")]),
        ModelResponse(
            parts=[TextPart(content="a1")],
            model_name="claude-sonnet-4-6",
            provider_name="anthropic",
        ),
        ModelRequest(parts=[UserPromptPart(content="q2")]),
        ModelResponse(
            parts=[TextPart(content="a2")],
            model_name="claude-opus-4-8",
            provider_name="anthropic",
        ),
    ]

    display = _rebuild_display_messages(messages, model_id="anthropic/claude-opus-4-8")

    assistants = [m for m in display if m["role"] == "assistant"]
    assert assistants[0]["model"] == "anthropic/claude-sonnet-4-6"
    assert assistants[1]["model"] == "anthropic/claude-opus-4-8"


def test_resolve_response_model():
    # Same provider: re-attach the run's config prefix to the response's model.
    assert (
        _resolve_response_model(
            "claude-sonnet-4-6", "anthropic/claude-opus-4-8", "anthropic"
        )
        == "anthropic/claude-sonnet-4-6"
    )
    # Provider switched mid-chat: use the response's own provider, not the run's.
    assert (
        _resolve_response_model("gpt-5", "anthropic/claude-opus-4-8", "openai")
        == "openai/gpt-5"
    )
    # OpenAI-compatible providers keep their configured provider prefix.
    assert (
        _resolve_response_model("mimo-v2.5-pro", "xiaomi_mimo/mimo-v2.5-pro", "openai")
        == "xiaomi_mimo/mimo-v2.5-pro"
    )
    # Gemini uses pydantic-ai's Google implementation provider internally.
    assert (
        _resolve_response_model("gemini-2.5-pro", "gemini/gemini-2.5-pro", "google-gla")
        == "gemini/gemini-2.5-pro"
    )
    # Aliased provider prefixes should also stay user-facing.
    assert (
        _resolve_response_model("glm-4.7-flash", "zai/glm-4.7-flash", "openai")
        == "zai/glm-4.7-flash"
    )
    # Older response without a model_name falls back to the run id.
    assert (
        _resolve_response_model(None, "anthropic/claude-opus-4-8", None)
        == "anthropic/claude-opus-4-8"
    )
    # Response already carrying a prefix is left untouched.
    assert (
        _resolve_response_model(
            "anthropic/claude-opus-4-8", "anthropic/claude-opus-4-8", "anthropic"
        )
        == "anthropic/claude-opus-4-8"
    )


def test_response_provider_matches_run_for_implementation_providers():
    assert _response_provider_matches_run("xiaomi_mimo", "openai")
    assert _response_provider_matches_run("gemini", "google-gla")
    assert _response_provider_matches_run("zai", "openai")
    assert not _response_provider_matches_run("anthropic", "openai")


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


def test_rebuild_display_messages_skips_compaction_summary():
    messages = [
        ModelRequest(parts=[UserPromptPart(content="original question")]),
        ModelResponse(parts=[TextPart(content="original answer")]),
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=f"{COMPACTION_SUMMARY_REQUEST_MARKER}\nsummary preface"
                )
            ]
        ),
        ModelResponse(
            parts=[
                TextPart(content=f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\nthe summary")
            ]
        ),
        ModelRequest(parts=[UserPromptPart(content="new question")]),
        ModelResponse(parts=[TextPart(content="new answer")]),
    ]

    display = _rebuild_display_messages(messages)

    contents = [m.get("content", "") for m in display]
    assert not any(COMPACTION_SUMMARY_REQUEST_MARKER in c for c in contents)
    assert not any(COMPACTION_SUMMARY_RESPONSE_MARKER in c for c in contents)
    assert any("original question" in c for c in contents)
    assert any("new answer" in c for c in contents)


def test_agent_history_is_compacted_detects_summary():
    not_compacted = [ModelRequest(parts=[UserPromptPart(content="hi")])]
    compacted = not_compacted + [
        ModelResponse(
            parts=[TextPart(content=f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\nx")]
        )
    ]
    assert _agent_history_is_compacted(not_compacted) is False
    assert _agent_history_is_compacted(compacted) is True


def test_merge_rebuilt_after_compaction_preserves_original_history():
    # Stored display log holds the full history, including this turn's pre-saved
    # user message. The compacted rebuild only covers the surviving tail.
    stored = [
        {"role": "user", "content": "old q1"},
        {"role": "assistant", "content": "old a1"},
        {"role": "user", "content": "old q2"},
        {"role": "assistant", "content": "old a2"},
        {"role": "user", "content": "new q"},
    ]
    rebuilt = [
        {"role": "user", "content": "old q2"},
        {"role": "assistant", "content": "old a2"},
        {"role": "user", "content": "new q"},
        {"role": "assistant", "content": "new a"},
    ]

    merged = _merge_rebuilt_after_compaction(stored, rebuilt)

    # Originals preserved, no duplication of the new user turn, new answer appended.
    assert [m["content"] for m in merged] == [
        "old q1",
        "old a1",
        "old q2",
        "old a2",
        "new q",
        "new a",
    ]


def test_merge_rebuilt_after_compaction_falls_back_without_stored():
    rebuilt = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    assert _merge_rebuilt_after_compaction([], rebuilt) == rebuilt


def test_merge_rebuilt_after_compaction_is_idempotent():
    # Post-process can run twice for a turn (retry, snapshot+finalize). The second
    # pass sees the assistant reply the first pass already appended. It must NOT
    # append it again (this is the "two identical responses after compact" bug).
    stored = [
        {"role": "user", "content": "old q"},
        {"role": "assistant", "content": "old a"},
        {"role": "user", "content": "new q"},
    ]
    rebuilt = [
        {"role": "user", "content": "new q"},
        {"role": "assistant", "content": "new a"},
    ]

    first = _merge_rebuilt_after_compaction(stored, rebuilt)
    assert [m["content"] for m in first] == ["old q", "old a", "new q", "new a"]

    # Feeding the result back in (as a later persist pass would) is stable.
    second = _merge_rebuilt_after_compaction(first, rebuilt)
    assert [m["content"] for m in second] == ["old q", "old a", "new q", "new a"]


def test_merge_rebuilt_after_compaction_no_duplicate_when_reply_already_stored():
    # Exact repro: the turn's user prompt is pre-written and a prior pass already
    # appended the assistant reply. Re-merging must not produce two replies.
    stored = [
        {"role": "assistant", "content": "prev turn"},
        {"role": "user", "content": "我们都聊了些啥"},
        {"role": "assistant", "content": "recap (optimistic, no thinking)"},
    ]
    rebuilt = [
        {"role": "user", "content": "我们都聊了些啥"},
        {"role": "assistant", "content": "recap (rebuilt, with thinking)"},
    ]

    merged = _merge_rebuilt_after_compaction(stored, rebuilt)

    assert [m["role"] for m in merged] == ["assistant", "user", "assistant"]
    # The rebuilt (authoritative) reply wins; there is exactly one assistant reply.
    assert merged[-1]["content"] == "recap (rebuilt, with thinking)"


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


def test_build_file_mention_context_accepts_host_paths():
    # In host mode a mention carries the real host path (e.g. a Windows
    # drive-letter path). Backslashes are normalized; traversal is rejected.
    context = _build_file_mention_context(
        [
            {"path": "D:/workspace/Multi Agents.md", "type": "file"},
            {"path": "D:\\workspace\\notes.md", "type": "file"},
            {"path": "C:/a/../b/escape.md", "type": "file"},
        ]
    )

    assert "[User referenced file: D:/workspace/Multi Agents.md]" in context
    assert "[User referenced file: D:/workspace/notes.md]" in context
    assert "escape.md" not in context


def test_strip_attachment_annotations_removes_file_reference_annotations():
    text = (
        "summarize this\n"
        "[User referenced file: /mnt/project/notes.md]\n"
        "[User referenced directory: /mnt/project/docs]"
    )

    assert _strip_attachment_annotations(text) == "summarize this"
