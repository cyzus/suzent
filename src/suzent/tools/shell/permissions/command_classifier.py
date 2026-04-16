from __future__ import annotations

from .policy_models import CommandClass, CommandContext

_READ_ONLY_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "rg",
    "find",
    "wc",
    "sort",
    "uniq",
    "stat",
    "file",
}

_WRITE_LIMITED_COMMANDS = {
    "mkdir",
    "touch",
    "cp",
    "mv",
    "rm",
    "rmdir",
    "sed",
}

_DANGEROUS_COMMANDS = {
    "sudo",
    "doas",
    "pkexec",
    "chmod",
    "chown",
    "dd",
    "mkfs",
    "poweroff",
    "reboot",
    "shutdown",
    "diskpart",
    "reg",
}


def classify_command(ctx: CommandContext) -> CommandClass:
    cmd = ctx.base_command
    if not cmd:
        return CommandClass.UNKNOWN

    if cmd in _DANGEROUS_COMMANDS:
        return CommandClass.DANGEROUS

    if cmd == "git":
        return CommandClass.UNKNOWN

    if cmd in _READ_ONLY_COMMANDS:
        return CommandClass.READ_ONLY

    if cmd in _WRITE_LIMITED_COMMANDS:
        return CommandClass.WRITE_LIMITED

    return CommandClass.UNKNOWN


def is_high_risk(ctx: CommandContext, command_class: CommandClass) -> bool:
    if command_class == CommandClass.DANGEROUS:
        return True

    return False
