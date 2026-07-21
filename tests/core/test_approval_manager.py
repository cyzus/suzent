from suzent.core.approval_manager import PendingApprovalSession
from suzent.core.stream_parser import ApprovalRequest
from suzent.permissions.actions import build_approval_decision


def test_remembered_modern_approval_uses_allow_session_action() -> None:
    decision = build_approval_decision(
        "bash_execute",
        {"content": "npm test"},
    ).model_dump(mode="json", by_alias=True)
    session = PendingApprovalSession(
        requests=[
            ApprovalRequest(
                request_id="call-1",
                tool_call_id="call-1",
                tool_name="bash_execute",
                args={"content": "npm test"},
                decision=decision,
            )
        ]
    )

    session.record(True, remember=True)

    assert session.to_resume_approvals()[0]["action_id"] == "allow_session"


def test_remembered_legacy_approval_keeps_legacy_payload() -> None:
    session = PendingApprovalSession(
        requests=[
            ApprovalRequest(
                request_id="call-1",
                tool_call_id="call-1",
                tool_name="bash_execute",
                args={"content": "npm test"},
            )
        ]
    )

    session.record(True, remember=True)

    approval = session.to_resume_approvals()[0]
    assert approval["remember"] == "session"
    assert "action_id" not in approval
