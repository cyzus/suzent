from __future__ import annotations

from .policy_models import CommandClass, CommandDecision, PermissionMode


def evaluate_mode(mode: PermissionMode, command_class: CommandClass) -> CommandDecision:
    if mode == PermissionMode.FULL_ACCESS:
        return CommandDecision.ALLOW

    if mode == PermissionMode.STRICT_READONLY:
        if command_class == CommandClass.READ_ONLY:
            return CommandDecision.ALLOW
        if command_class == CommandClass.DANGEROUS:
            return CommandDecision.DENY
        return CommandDecision.ASK

    if mode == PermissionMode.ACCEPT_EDITS:
        if command_class in {CommandClass.READ_ONLY, CommandClass.WRITE_LIMITED}:
            return CommandDecision.ALLOW
        if command_class == CommandClass.DANGEROUS:
            return CommandDecision.DENY
        return CommandDecision.ASK

    # FULL_APPROVAL (the default mode): ask before state-changing operations,
    # but read-only commands (ls, cat, …) are not state-changing, so allow them
    # without a prompt rather than interrupting on every benign inspection.
    if command_class == CommandClass.READ_ONLY:
        return CommandDecision.ALLOW
    if command_class == CommandClass.DANGEROUS:
        return CommandDecision.DENY
    return CommandDecision.ASK
