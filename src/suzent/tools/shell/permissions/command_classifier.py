from __future__ import annotations

from .command_catalog import (
    DANGEROUS_COMMANDS,
    DESTRUCTIVE_COMMANDS,
    READ_ONLY_COMMANDS,
    WRITE_LIMITED_COMMANDS,
    find_is_read_only,
    sed_is_read_only,
)
from .policy_models import CommandClass, CommandContext


def classify_command(ctx: CommandContext) -> CommandClass:
    cmd = ctx.base_command
    if not cmd:
        return CommandClass.UNKNOWN

    if cmd in DANGEROUS_COMMANDS:
        return CommandClass.DANGEROUS

    if cmd == "git":
        return CommandClass.UNKNOWN

    # Destructive commands are never trusted on base name alone; ASK (which the
    # Auto classifier then evaluates in auto mode).
    if cmd in DESTRUCTIVE_COMMANDS:
        return CommandClass.UNKNOWN

    if cmd == "find":
        return (
            CommandClass.READ_ONLY if find_is_read_only(ctx) else CommandClass.UNKNOWN
        )

    if cmd == "sed":
        # Read-only sed (no in-place / no `e`) is a safe stream filter; an
        # editing or executing sed falls through to the classifier.
        return CommandClass.READ_ONLY if sed_is_read_only(ctx) else CommandClass.UNKNOWN

    if cmd in READ_ONLY_COMMANDS:
        return CommandClass.READ_ONLY

    if cmd in WRITE_LIMITED_COMMANDS:
        return CommandClass.WRITE_LIMITED

    return CommandClass.UNKNOWN
