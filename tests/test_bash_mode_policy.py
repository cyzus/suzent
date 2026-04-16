from suzent.tools.shell.permissions.mode_policy import evaluate_mode
from suzent.tools.shell.permissions.policy_models import (
    CommandClass,
    CommandDecision,
    PermissionMode,
)


def test_strict_readonly_denies_write_limited():
    decision = evaluate_mode(PermissionMode.STRICT_READONLY, CommandClass.WRITE_LIMITED)
    assert decision == CommandDecision.ASK


def test_accept_edits_allows_write_limited():
    decision = evaluate_mode(PermissionMode.ACCEPT_EDITS, CommandClass.WRITE_LIMITED)
    assert decision == CommandDecision.ALLOW


def test_full_approval_asks_unknown():
    decision = evaluate_mode(PermissionMode.FULL_APPROVAL, CommandClass.UNKNOWN)
    assert decision == CommandDecision.ASK
