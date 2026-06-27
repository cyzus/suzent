from __future__ import annotations

from .policy_models import BashCommandPolicyRule, CommandDecision


def normalize_rules(raw_rules: list[dict] | None) -> list[BashCommandPolicyRule]:
    if not raw_rules:
        return []

    rules: list[BashCommandPolicyRule] = []
    for item in raw_rules:
        try:
            pattern = str(item.get("pattern", "")).strip()
            match_type = str(item.get("match_type", "exact")).strip().lower()
            action = str(item.get("action", "ask")).strip().lower()
            if not pattern:
                continue
            if match_type not in {"exact", "prefix"}:
                continue
            if action not in {"allow", "ask", "deny"}:
                continue
            rules.append(
                BashCommandPolicyRule(
                    pattern=pattern,
                    match_type=match_type,
                    action=CommandDecision(action),
                )
            )
        except Exception:
            continue
    return rules


def _resolve_match_actions(rules: list[BashCommandPolicyRule]) -> CommandDecision:
    if any(rule.action == CommandDecision.DENY for rule in rules):
        return CommandDecision.DENY
    if any(rule.action == CommandDecision.ASK for rule in rules):
        return CommandDecision.ASK
    return CommandDecision.ALLOW


def evaluate_rules(
    command_text: str, rules: list[BashCommandPolicyRule]
) -> CommandDecision | None:
    text = command_text.strip()
    if not text or not rules:
        return None

    exact_matches = [r for r in rules if r.match_type == "exact" and r.pattern == text]
    if exact_matches:
        return _resolve_match_actions(exact_matches)

    prefix_matches = [
        r for r in rules if r.match_type == "prefix" and text.startswith(r.pattern)
    ]
    if prefix_matches:
        return _resolve_match_actions(prefix_matches)

    return None
