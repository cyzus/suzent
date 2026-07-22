from types import SimpleNamespace

from suzent.core.chat_processor import _resolve_resume_approval_actions
from suzent.core.social_brain import (
    _ensure_approval_decision,
    _persist_pending_approval_session,
)
from suzent.core.stream_parser import ApprovalRequest
from suzent.permissions.actions import build_approval_decision


class FakeDatabase:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(config={})

    def get_chat(self, chat_id: str):
        assert chat_id == "social-wechat-user-1"
        return self.chat

    def merge_chat_config(self, chat_id: str, updates: dict) -> bool:
        assert chat_id == "social-wechat-user-1"
        self.chat.config = {**self.chat.config, **updates}
        return True


def test_social_pending_approval_persistence_supports_ya_remember(
    monkeypatch,
) -> None:
    decision = build_approval_decision(
        "bash_execute",
        {"content": "npm test"},
    ).model_dump(mode="json", by_alias=True)
    db = FakeDatabase()
    monkeypatch.setattr("suzent.core.social_brain.get_database", lambda: db)
    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: db)

    _persist_pending_approval_session(
        "social-wechat-user-1",
        [
            ApprovalRequest(
                request_id="call-1",
                tool_call_id="call-1",
                tool_name="bash_execute",
                args={"content": "npm test"},
                decision=decision,
            )
        ],
    )

    resolved = _resolve_resume_approval_actions(
        "social-wechat-user-1",
        [
            {
                "request_id": "call-1",
                "tool_call_id": "call-1",
                "action_id": "allow_session",
            }
        ],
    )

    assert resolved[0]["remember"] == "session"
    assert resolved[0]["_permission_updates"][0]["payload"]["tool"] == "bash_execute"


def test_social_pending_approval_persistence_deduplicates_by_tool_call_id(
    monkeypatch,
) -> None:
    decision = build_approval_decision("write_file", {}).model_dump(
        mode="json",
        by_alias=True,
    )
    db = FakeDatabase()
    db.chat.config = {
        "_pending_approvals": [
            {
                "approvalId": "call-1",
                "toolCallId": "call-1",
                "toolName": "write_file",
                "args": {},
                "decision": {},
            }
        ]
    }
    monkeypatch.setattr("suzent.core.social_brain.get_database", lambda: db)

    _persist_pending_approval_session(
        "social-wechat-user-1",
        [
            ApprovalRequest(
                request_id="call-1",
                tool_call_id="call-1",
                tool_name="write_file",
                args={"file_path": "README.md"},
                decision=decision,
            )
        ],
    )

    approvals = db.chat.config["_pending_approvals"]
    assert len(approvals) == 1
    assert approvals[0]["args"] == {"file_path": "README.md"}


def test_social_missing_decision_is_hydrated_for_tool_wide_remember() -> None:
    req = ApprovalRequest(
        request_id="call-1",
        tool_call_id="call-1",
        tool_name="social_message",
        args={
            "channel": "wechat",
            "recipient": "user-1@im.wechat",
            "message": "volatile message text",
        },
    )

    hydrated = _ensure_approval_decision(req)

    allow_session = next(
        action
        for action in hydrated.decision["actions"]
        if action["id"] == "allow_session"
    )
    update = allow_session["permissionUpdates"][0]
    assert update["payload"]["tool"] == "social_message"
    assert update["payload"]["matcher"] == {"type": "all"}
