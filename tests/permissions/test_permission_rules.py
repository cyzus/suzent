from __future__ import annotations

from suzent.permissions.models import PermissionRule
from suzent.permissions.rules import match_rule, parse_rules


def command_prefix_rule(prefix: str) -> PermissionRule:
    return PermissionRule.model_validate(
        {
            "tool": "bash_execute",
            "behavior": "allow",
            "matcher": {"type": "command_prefix", "value": prefix},
        }
    )


def test_command_prefix_matches_normalized_command_name() -> None:
    rule = command_prefix_rule("get-childitem")

    assert match_rule(
        rule,
        "bash_execute",
        {
            "content": (
                'Get-ChildItem -Path "C:\\Users\\example\\.suzent\\" '
                '-Filter "*.ts" -Recurse -Depth 2'
            )
        },
    )


def test_command_prefix_preserves_subcommand_case_sensitivity() -> None:
    rule = command_prefix_rule("git show")

    assert match_rule(rule, "bash_execute", {"content": "Git show HEAD"})
    assert not match_rule(rule, "bash_execute", {"content": "git SHOW HEAD"})


def test_command_prefix_does_not_match_control_operator_chain() -> None:
    rule = command_prefix_rule("git log")

    assert not match_rule(
        rule,
        "bash_execute",
        {"content": "git log --oneline && git push"},
    )


def test_legacy_process_poll_rule_migrates_its_input_shape() -> None:
    rules = parse_rules(
        [
            {
                "tool": "process_manage",
                "behavior": "deny",
                "matcher": {
                    "type": "exact_input",
                    "value": {
                        "action": "poll",
                        "process_id": "abcdef123456",
                        "offset": 12,
                    },
                },
            }
        ]
    )

    assert len(rules) == 1
    assert rules[0].tool == "check_command"
    assert rules[0].matcher.value == {
        "command_id": "abcdef123456",
        "offset": 12,
    }
    assert match_rule(
        rules[0],
        "check_command",
        {"command_id": "abcdef123456", "offset": 12},
    )


def test_legacy_process_kill_rule_migrates_its_input_shape() -> None:
    rules = parse_rules(
        [
            {
                "tool": "ProcessTool",
                "behavior": "deny",
                "matcher": {
                    "type": "exact_input",
                    "value": {
                        "action": "kill",
                        "process_id": "abcdef123456",
                        "offset": 12,
                    },
                },
            }
        ]
    )

    assert len(rules) == 1
    assert rules[0].tool == "stop_command"
    assert rules[0].matcher.value == {"command_id": "abcdef123456"}
    assert match_rule(
        rules[0],
        "stop_command",
        {"command_id": "abcdef123456"},
    )
