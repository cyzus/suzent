"""A resume whose approvals have all expired must not run the agent.

Running it anyway starts a fresh turn: the model re-issues the call under a new
id and policy, not the user, decides it -- the user's choice is silently lost.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)

from suzent.core.agent_serializer import deserialize_state, serialize_state
from suzent.core.chat_processor import (
    APPROVAL_EXPIRED_NOTICE,
    ChatProcessor,
    _collect_unprocessed_tool_call_ids,
)


class _Agent:
    _model_id = "model-test"
    _tool_names: list[str] = []
    _last_messages: list = []


def _events(chunks):
    return [
        json.loads(chunk[6:].strip())
        for chunk in chunks
        if chunk.startswith("data: ") and chunk[6:].strip() != "[DONE]"
    ]


@pytest.mark.asyncio
async def test_resume_with_only_expired_approvals_settles_the_card_without_running(
    temp_db, monkeypatch
):
    history = [
        ModelRequest(parts=[UserPromptPart(content="get the key")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="run_command",
                    tool_call_id="call-1",
                    args={"content": "cat config.xml"},
                )
            ]
        ),
    ]
    pending_card = {
        "role": "assistant",
        "content": (
            '<details data-tool-call-id="call-1" data-approval-id="call-1" '
            'data-approval-state="pending"><summary>run_command</summary></details>'
        ),
        "parts": [
            {
                "type": "tool",
                "toolCallId": "call-1",
                "toolName": "run_command",
                "args": "cat config.xml",
                "state": "approval-requested",
                "approvalId": "call-1",
            }
        ],
    }
    chat_id = temp_db.create_chat(
        title="Expired",
        config={},
        messages=[{"role": "user", "content": "get the key"}, pending_card],
        agent_state=serialize_state(history),
    )

    async def get_agent(config):
        return _Agent()

    def must_not_stream(*args, **kwargs):
        raise AssertionError("the agent ran on an expired approval")

    monkeypatch.setattr("suzent.core.chat_processor.get_or_create_agent", get_agent)
    monkeypatch.setattr(
        "suzent.core.chat_processor.build_agent_deps",
        lambda chat_id, user_id, config: SimpleNamespace(
            last_messages=None,
            cancel_event=None,
            is_suspended=False,
            inline_a2ui_surfaces={},
        ),
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.stream_agent_responses", must_not_stream
    )

    with patch("suzent.core.chat_processor.get_database", return_value=temp_db):
        chunks = [
            chunk
            async for chunk in ChatProcessor().process_turn(
                message_content="",
                chat_id=chat_id,
                user_id="u",
                resume_approvals=[
                    {
                        "request_id": "call-1",
                        "tool_call_id": "call-1",
                        "approved": True,
                        "action_id": "allow_once",
                    }
                ],
            )
        ]

    events = _events(chunks)
    results = [
        e["value"]
        for e in events
        if e.get("type") == "CUSTOM" and e.get("name") == "tool_approval_result"
    ]
    assert results == [
        {
            "toolCallId": "call-1",
            "toolName": "run_command",
            "status": "expired",
            "output": APPROVAL_EXPIRED_NOTICE,
        }
    ]
    assert any(APPROVAL_EXPIRED_NOTICE in str(e.get("delta") or "") for e in events)
    # The client reloads from the database when the stream ends, so the
    # settled state has to be stored, not only streamed.
    chat = temp_db.get_chat(chat_id)
    assert chat.messages[-1] == {"role": "notice", "content": APPROVAL_EXPIRED_NOTICE}
    card = chat.messages[-2]
    assert card["parts"][0]["state"] == "error"
    assert card["parts"][0]["output"] == APPROVAL_EXPIRED_NOTICE
    assert "approvalId" not in card["parts"][0]
    assert 'data-approval-state="denied"' in card["content"]
    stored_history = deserialize_state(chat.agent_state)["message_history"]
    assert _collect_unprocessed_tool_call_ids(stored_history) == set()
