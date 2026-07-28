from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from suzent.core.agent_serializer import deserialize_state, serialize_state
from suzent.core.fork import (
    _agent_state_at_display_point,
    _raw_index_at_logical_display_point,
    fork_chat,
)
from suzent.database import ChatDatabase


def test_agent_state_can_branch_at_any_assistant_message():
    history = [
        ModelRequest(parts=[UserPromptPart(content="first question")]),
        ModelResponse(parts=[TextPart(content="first answer")]),
        ModelRequest(parts=[UserPromptPart(content="second question")]),
        ModelResponse(parts=[TextPart(content="second answer")]),
    ]
    display_messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "second answer"},
    ]

    branch_state = _agent_state_at_display_point(
        serialize_state(history, model_id="test-model"),
        display_messages,
        turn_index=2,
    )

    restored = deserialize_state(branch_state)
    assert restored is not None
    assert restored["model_id"] == "test-model"
    assert len(restored["message_history"]) == 2
    assert isinstance(restored["message_history"][-1], ModelResponse)


def test_agent_state_falls_back_to_visible_conversation():
    display_messages = [
        {"role": "user", "content": "question"},
        {
            "role": "assistant",
            "content": "rendered content",
            "parts": [
                {"type": "reasoning", "text": "private reasoning"},
                {"type": "text", "text": "visible answer"},
            ],
        },
    ]

    branch_state = _agent_state_at_display_point(None, display_messages, turn_index=2)

    restored = deserialize_state(branch_state)
    assert restored is not None
    history = restored["message_history"]
    assert len(history) == 2
    assert history[-1].parts[0].content == "visible answer"


def test_logical_branch_point_includes_merged_tool_activity():
    messages = [
        {"role": "user", "content": "question"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call-1"}],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "result"},
        {"role": "assistant", "content": "final answer"},
        {"role": "user", "content": "next question"},
        {"role": "assistant", "content": "next answer"},
    ]

    assert _raw_index_at_logical_display_point(messages, logical_index=2) == 4
    assert _raw_index_at_logical_display_point(messages, logical_index=4) == 6


def test_fork_chat_branches_history_without_changing_workspace(
    temp_db: ChatDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = [
        ModelRequest(parts=[UserPromptPart(content="first question")]),
        ModelResponse(parts=[TextPart(content="first answer")]),
        ModelRequest(parts=[UserPromptPart(content="second question")]),
        ModelResponse(parts=[TextPart(content="second answer")]),
    ]
    display_messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "second answer"},
    ]
    source_id = temp_db.create_chat(
        "Original",
        {},
        display_messages,
        agent_state=serialize_state(history),
        working_directory=str(tmp_path),
    )
    workspace_file = tmp_path / "current.txt"
    workspace_file.write_text("current workspace", encoding="utf-8")

    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    monkeypatch.setattr(
        "suzent.config.CONFIG.sandbox_data_path",
        str(tmp_path / "sandbox"),
    )

    branch_id, restored_files = fork_chat(source_id, turn_index=2)

    branch = temp_db.get_chat(branch_id)
    assert branch is not None
    assert branch.messages == display_messages[:2]
    assert branch.config["forked_from_chat_id"] == source_id
    assert branch.config["forked_from_chat_title"] == "Original"
    assert branch.config["forked_from_message_index"] == 2
    branch_state = deserialize_state(branch.agent_state)
    assert branch_state is not None
    assert len(branch_state["message_history"]) == 2
    assert restored_files == []
    assert workspace_file.read_text(encoding="utf-8") == "current workspace"
