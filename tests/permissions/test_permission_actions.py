from __future__ import annotations

import pytest

from suzent.permissions.actions import (
    build_approval_decision,
    derive_command_prefix,
    resolve_action,
)


def test_derive_command_prefix_smart_subcommand() -> None:
    assert derive_command_prefix("git log --oneline -5") == "git log"
    assert derive_command_prefix("npm run build") == "npm run"
    # Non-subcommand tool: just the base command.
    assert derive_command_prefix("ls -la") == "ls"
    # Env-var prefix is stripped by the shared parser.
    assert derive_command_prefix("FOO=1 git status") == "git status"
    # Control operators make a prefix rule misleading -> no prefix.
    assert derive_command_prefix("git log && rm -rf /") == ""
    assert derive_command_prefix("") == ""


def test_derive_command_prefix_suzent_cli_two_levels() -> None:
    # suzent is a nested Typer CLI: keep sub-app + verb.
    assert derive_command_prefix("suzent config set foo bar") == "suzent config set"
    assert derive_command_prefix("suzent agent approve") == "suzent agent approve"
    assert derive_command_prefix("suzent cron add --name x") == "suzent cron add"
    # Only one subcommand available -> prefix is base + that token.
    assert derive_command_prefix("suzent status") == "suzent status"


def test_bash_remember_uses_prefix_matcher_for_subcommand() -> None:
    decision = build_approval_decision(
        "bash_execute",
        {"content": "git log --oneline -5"},
    ).model_dump(mode="json", by_alias=True)

    # Exactly one session + one global remember option, scoped to the prefix.
    ids = [action["id"] for action in decision["actions"]]
    assert ids == ["allow_once", "allow_session", "allow_global", "reject"]
    for action_id in ("allow_session", "allow_global"):
        action = next(a for a in decision["actions"] if a["id"] == action_id)
        assert action["permissionUpdates"][0]["payload"]["matcher"] == {
            "type": "command_prefix",
            "value": "git log",
        }


def test_bash_remember_falls_back_to_exact_when_prefix_equals_command() -> None:
    # "npm test" derives prefix "npm test" == full command, so remember on exact.
    decision = build_approval_decision(
        "bash_execute",
        {"content": "npm test"},
    ).model_dump(mode="json", by_alias=True)
    ids = [action["id"] for action in decision["actions"]]
    assert ids == ["allow_once", "allow_session", "allow_global", "reject"]
    action = next(a for a in decision["actions"] if a["id"] == "allow_global")
    assert action["permissionUpdates"][0]["payload"]["matcher"] == {
        "type": "exact_input",
        "value": {"command": "npm test"},
    }


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
