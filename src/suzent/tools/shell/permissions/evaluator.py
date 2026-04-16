from __future__ import annotations

from .command_classifier import classify_command, is_high_risk
from .command_parser import parse_command
from .mode_policy import evaluate_mode
from .path_extractor import extract_path_uses
from .path_policy import validate_paths
from .policy_models import (
    CommandClass,
    CommandDecision,
    PermissionEvaluation,
    PermissionMode,
)
from .rule_engine import evaluate_rules, normalize_rules


def _parse_mode(mode_value: str | None) -> PermissionMode:
    if not mode_value:
        return PermissionMode.FULL_APPROVAL
    lowered = mode_value.strip().lower()
    for mode in PermissionMode:
        if mode.value == lowered:
            return mode
    return PermissionMode.FULL_APPROVAL


def evaluate_command_policy(
    command_text: str,
    resolver,
    mode_value: str | None = None,
    raw_rules: list[dict] | None = None,
    default_action: str = "ask",
) -> PermissionEvaluation:
    ctx = parse_command(command_text)
    command_class = classify_command(ctx)

    if ctx.has_control_operators:
        return PermissionEvaluation(
            decision=CommandDecision.ASK,
            reason="Command requires approval due to shell chaining semantics",
            command_class=CommandClass.UNKNOWN,
            metadata={"base_command": ctx.base_command},
        )

    if ctx.base_command == "git":
        return PermissionEvaluation(
            decision=CommandDecision.ASK,
            reason="Git commands require approval",
            command_class=CommandClass.UNKNOWN,
            metadata={"base_command": ctx.base_command},
        )

    if is_high_risk(ctx, command_class):
        return PermissionEvaluation(
            decision=CommandDecision.DENY,
            reason="Command blocked by high-risk shell semantics",
            command_class=CommandClass.DANGEROUS,
            metadata={"base_command": ctx.base_command},
        )

    path_eval = validate_paths(extract_path_uses(ctx), resolver)
    if path_eval is not None:
        path_eval.metadata["base_command"] = ctx.base_command
        return path_eval

    rules = normalize_rules(raw_rules)
    rule_decision = evaluate_rules(command_text, rules)
    if rule_decision is not None:
        return PermissionEvaluation(
            decision=rule_decision,
            reason="Decision from command policy rule",
            command_class=command_class,
            metadata={"base_command": ctx.base_command},
        )

    mode = _parse_mode(mode_value)
    mode_decision = evaluate_mode(mode, command_class)
    if mode == PermissionMode.FULL_APPROVAL and mode_decision == CommandDecision.ASK:
        fallback = default_action.strip().lower()
        if fallback == "deny":
            mode_decision = CommandDecision.DENY

    return PermissionEvaluation(
        decision=mode_decision,
        reason="Decision from permission mode",
        command_class=command_class,
        metadata={"base_command": ctx.base_command, "mode": mode.value},
    )
