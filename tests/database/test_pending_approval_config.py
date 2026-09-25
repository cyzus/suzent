from unittest.mock import patch

from suzent.core.chat_processor import _resolve_resume_approval_actions
from suzent.permissions.actions import build_approval_decision


def test_config_save_preserves_pending_approval_for_resume(temp_db) -> None:
    chat = temp_db.create_chat(
        title="Approval test", config={"permission_mode": "auto"}
    )
    decision = build_approval_decision(
        "edit_image", {}, reason="Needs approval", reason_code="test"
    ).model_dump(mode="json", by_alias=True)
    pending = [
        {
            "approvalId": "call-edit",
            "toolCallId": "call-edit",
            "toolName": "edit_image",
            "args": {},
            "decision": decision,
        }
    ]
    temp_db.merge_chat_config(chat, {"_pending_approvals": pending})
    temp_db.update_chat(chat, config={"permission_mode": "auto"}, messages=[])
    with patch("suzent.core.chat_processor.get_database", return_value=temp_db):
        resolved = _resolve_resume_approval_actions(
            chat, [{"request_id": "call-edit", "action_id": "allow_once"}]
        )
    assert len(resolved) == 1
    assert resolved[0]["approved"] is True
    assert resolved[0]["tool_call_id"] == "call-edit"
    assert resolved[0]["remember"] == ""


def test_stale_config_cannot_restore_resolved_approval(temp_db) -> None:
    chat = temp_db.create_chat(title="Approval test", config={})
    stale = {"_pending_approvals": [{"approvalId": "old-call"}]}
    temp_db.merge_chat_config(chat, {"_pending_approvals": []})
    temp_db.update_chat(chat, config=stale)
    assert temp_db.get_chat(chat).config["_pending_approvals"] == []
