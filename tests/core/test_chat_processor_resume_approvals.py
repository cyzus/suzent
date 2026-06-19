from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.tools import ToolDenied

from suzent.core.chat_processor import (
    _collect_unprocessed_tool_call_ids,
    _deferred_approval_result,
    _resolve_resume_approval_actions,
)
from suzent.permissions.actions import build_approval_decision


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


def test_deferred_denial_attaches_user_feedback_to_tool_result() -> None:
    result = _deferred_approval_result(
        {
            "approved": False,
            "feedback": "Use the staging environment instead",
        }
    )

    assert isinstance(result, ToolDenied)
    assert result.message == (
        "The user denied this tool call and provided guidance: "
        "Use the staging environment instead"
    )


def test_deferred_denial_without_feedback_uses_framework_message() -> None:
    result = _deferred_approval_result({"approved": False})

    assert isinstance(result, ToolDenied)
    assert result.message == "The tool call was denied."


def test_deferred_approval_remains_executable() -> None:
    assert _deferred_approval_result({"approved": True}) is True


def test_resolve_resume_action_from_persisted_contract(monkeypatch) -> None:
    decision = build_approval_decision(
        "bash_execute",
        {"content": "npm test"},
    ).model_dump(mode="json", by_alias=True)

    class Chat:
        config = {
            "_pending_approvals": [
                {
                    "approvalId": "call-1",
                    "toolCallId": "call-1",
                    "toolName": "bash_execute",
                    "args": {"content": "npm test"},
                    "decision": decision,
                }
            ]
        }

    class Database:
        def get_chat(self, chat_id: str):
            assert chat_id == "chat-1"
            return Chat()

    monkeypatch.setattr(
        "suzent.core.chat_processor.get_database",
        lambda: Database(),
    )

    resolved = _resolve_resume_approval_actions(
        "chat-1",
        [
            {
                "approval_id": "call-1",
                "tool_call_id": "call-1",
                "action_id": "allow_session",
            }
        ],
    )

    assert resolved[0]["approved"] is True
    assert resolved[0]["remember"] == "session"
    assert resolved[0]["tool_name"] == "bash_execute"
    assert resolved[0]["args"] == {"content": "npm test"}


def test_resume_action_uses_persisted_args_not_client_args(monkeypatch) -> None:
    decision = build_approval_decision(
        "bash_execute",
        {"content": "npm test"},
    ).model_dump(mode="json", by_alias=True)

    class Chat:
        config = {
            "_pending_approvals": [
                {
                    "approvalId": "call-1",
                    "toolCallId": "call-1",
                    "toolName": "bash_execute",
                    "args": {"content": "npm test"},
                    "decision": decision,
                }
            ]
        }

    class Database:
        def get_chat(self, _chat_id: str):
            return Chat()

    monkeypatch.setattr(
        "suzent.core.chat_processor.get_database",
        lambda: Database(),
    )

    resolved = _resolve_resume_approval_actions(
        "chat-1",
        [
            {
                "approval_id": "call-1",
                "action_id": "allow_global",
                "args": {"content": "npm publish"},
            }
        ],
    )

    assert resolved[0]["args"] == {"content": "npm test"}
    update = resolved[0]["_permission_updates"][0]
    assert update["payload"]["matcher"]["value"]["command"] == "npm test"


def test_legacy_resume_cannot_persist_permission(monkeypatch) -> None:
    class Database:
        def get_chat(self, _chat_id: str):
            return None

    monkeypatch.setattr(
        "suzent.core.chat_processor.get_database",
        lambda: Database(),
    )

    resolved = _resolve_resume_approval_actions(
        "chat-1",
        [
            {
                "approval_id": "call-1",
                "approved": True,
                "remember": "global",
            }
        ],
    )

    assert resolved[0]["approved"] is True
    assert resolved[0]["remember"] == ""
