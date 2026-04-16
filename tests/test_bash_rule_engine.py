from suzent.tools.shell.permissions.rule_engine import evaluate_rules, normalize_rules
from suzent.tools.shell.permissions.policy_models import CommandDecision


def test_rule_engine_exact_deny_overrides_allow():
    rules = normalize_rules(
        [
            {"pattern": "ls", "match_type": "exact", "action": "allow"},
            {"pattern": "ls", "match_type": "exact", "action": "deny"},
        ]
    )

    decision = evaluate_rules("ls", rules)

    assert decision == CommandDecision.DENY


def test_rule_engine_prefix_allow():
    rules = normalize_rules(
        [{"pattern": "git status", "match_type": "prefix", "action": "allow"}]
    )

    decision = evaluate_rules("git status -s", rules)

    assert decision == CommandDecision.ALLOW
