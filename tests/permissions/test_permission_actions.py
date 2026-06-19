from __future__ import annotations

import pytest

from suzent.permissions.actions import build_approval_decision, resolve_action


def test_bash_approval_actions_use_exact_command_matcher() -> None:
    decision = build_approval_decision(
        "bash_execute",
        {"content": "npm test", "description": "Run tests"},
    ).model_dump(mode="json", by_alias=True)

    assert decision["behavior"] == "ask"
    assert [action["id"] for action in decision["actions"]] == [
        "allow_once",
        "allow_session",
        "allow_global",
        "reject",
    ]
    assert decision["actions"][1]["permissionUpdates"][0]["payload"]["matcher"] == {
        "type": "exact_input",
        "value": {"command": "npm test"},
    }


def test_non_bash_approval_actions_use_tool_wide_matcher() -> None:
    decision = build_approval_decision(
        "write_file",
        {"file_path": "README.md"},
    ).model_dump(mode="json", by_alias=True)

    assert decision["actions"][1]["permissionUpdates"][0]["payload"]["matcher"] == {
        "type": "all"
    }


def test_inline_python_execution_only_offers_one_time_actions() -> None:
    decision = build_approval_decision(
        "bash_execute",
        {"content": "print('hello')", "language": "python"},
    ).model_dump(mode="json", by_alias=True)

    assert [action["id"] for action in decision["actions"]] == [
        "allow_once",
        "reject",
    ]


def test_resolve_action_returns_legacy_approval_values() -> None:
    decision = build_approval_decision("write_file", {}).model_dump(
        mode="json", by_alias=True
    )

    assert resolve_action(decision, "allow_once") == (True, "")
    assert resolve_action(decision, "allow_session") == (True, "session")
    assert resolve_action(decision, "allow_global") == (True, "global")
    assert resolve_action(decision, "reject") == (False, "")


def test_resolve_action_rejects_unoffered_action() -> None:
    decision = build_approval_decision("write_file", {}).model_dump(
        mode="json", by_alias=True
    )

    with pytest.raises(ValueError, match="was not offered"):
        resolve_action(decision, "allow_everything")
