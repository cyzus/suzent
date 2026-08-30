from __future__ import annotations

from .command_classifier import classify_command
from .command_parser import parse_command
from .mode_policy import evaluate_mode
from .path_extractor import extract_path_uses
from .path_policy import validate_dangerous_paths, validate_paths
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
    mode = _parse_mode(mode_value)

    if ctx.has_control_operators and mode != PermissionMode.FULL_ACCESS:
        return PermissionEvaluation(
            decision=CommandDecision.ASK,
            reason="Command requires approval due to shell chaining semantics",
            command_class=CommandClass.UNKNOWN,
            metadata={"base_command": ctx.base_command},
        )

    if ctx.base_command == "git" and mode != PermissionMode.FULL_ACCESS:
        return PermissionEvaluation(
            decision=CommandDecision.ASK,
            reason="Git commands require approval",
            command_class=CommandClass.UNKNOWN,
            metadata={"base_command": ctx.base_command},
        )

    if command_class == CommandClass.DANGEROUS:
        return PermissionEvaluation(
            decision=CommandDecision.DENY,
            reason="Command blocked by high-risk shell semantics",
            command_class=CommandClass.DANGEROUS,
            metadata={"base_command": ctx.base_command},
        )

    path_uses = extract_path_uses(ctx)

    # Catastrophic targets (rm -rf /, /etc, C:/Windows) are never approvable.
    dangerous_paths = validate_dangerous_paths(path_uses)
    if dangerous_paths is not None:
        dangerous_paths.metadata["base_command"] = ctx.base_command
        return dangerous_paths

    path_eval = validate_paths(path_uses, resolver)

    # Under the sandbox the resolver backs real containment, so a path it cannot
    # reach is refused outright — no rule and no mode negotiates that.
    if path_eval is not None and path_eval.decision == CommandDecision.DENY:
        path_eval.metadata["base_command"] = ctx.base_command
        return path_eval

    rules = normalize_rules(raw_rules)
    rule_decision = evaluate_rules(command_text, rules)
    if rule_decision is not None:
        if mode == PermissionMode.FULL_ACCESS and rule_decision == CommandDecision.ASK:
            rule_decision = CommandDecision.ALLOW
        return PermissionEvaluation(
            decision=rule_decision,
            reason="Decision from command policy rule",
            command_class=command_class,
            metadata={"base_command": ctx.base_command},
        )

    mode_decision = evaluate_mode(mode, command_class)

    # On the host the same check is advisory: it can upgrade a mode decision to
    # ASK, and only that. It sits below the rules and the mode so an explicit
    # rule can authorize the folder the user asked the agent to work in, and so
    # Full Access still means what it says. As a gate above them it was
    # unappealable, and it only ever saw the handful of commands the catalog
    # extracts paths for — filtering command names, not access.
    if (
        path_eval is not None
        and mode_decision == CommandDecision.ALLOW
        and mode != PermissionMode.FULL_ACCESS
    ):
        path_eval.metadata["base_command"] = ctx.base_command
        path_eval.metadata["mode"] = mode.value
        return path_eval

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
