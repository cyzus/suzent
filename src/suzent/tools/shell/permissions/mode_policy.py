from __future__ import annotations

from .policy_models import CommandClass, CommandDecision, PermissionMode


def evaluate_mode(mode: PermissionMode, command_class: CommandClass) -> CommandDecision:
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

    # FULL_APPROVAL
    if command_class == CommandClass.DANGEROUS:
        return CommandDecision.DENY
    return CommandDecision.ASK
