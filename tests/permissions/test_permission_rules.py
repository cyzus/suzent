from __future__ import annotations

from suzent.permissions.models import PermissionRule
from suzent.permissions.rules import match_rule


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
