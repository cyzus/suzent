from __future__ import annotations

from .policy_models import CommandClass, CommandContext

_READ_ONLY_COMMANDS = {
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "rg",
    "wc",
    "sort",
    "uniq",
    "stat",
    "file",
}

# Commands that create or copy but do not destroy existing data. These stay
# auto-allowable under accept-edits / auto mode, matching the workspace
# file-write fast path.
_WRITE_LIMITED_COMMANDS = {
    "mkdir",
    "touch",
    "cp",
}

# Destructive or in-place-rewriting commands. Even inside the workspace these
# are not auto-allowed by mode alone: they fall through to ASK (and therefore to
# the Auto classifier in auto mode) instead of being trusted on base name.
_DESTRUCTIVE_COMMANDS = {
    "rm",
    "rmdir",
    "mv",
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

# find flags that delete or run other programs, making the invocation mutating
# or code-executing rather than read-only.
_FIND_MUTATING_FLAGS = {
    "-delete",
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",
    "-fprint",
    "-fprintf",
    "-fprint0",
    "-fls",
}


def _find_is_read_only(ctx: CommandContext) -> bool:
    """`find` only reads unless it is told to delete or execute."""
    return not any(arg in _FIND_MUTATING_FLAGS for arg in ctx.args)


def _sed_is_read_only(ctx: CommandContext) -> bool:
    """`sed` is read-only unless it edits in place or runs the `e` command.

    `-i`/`--in-place` rewrites files, and the `e` command (either the bare `e`
    or the `e` flag on an `s///` substitution) executes an external shell. Note
    that `-e`/`--expression` is the ordinary way to pass a script and is NOT a
    mutation signal, so it must not be confused with the `e` command.
    """
    expects_script = False
    for arg in ctx.args:
        is_flag = arg.startswith("-")
        is_long_flag = arg.startswith("--")
        # In-place editing rewrites files: `--in-place[=SUFFIX]`, or any short
        # flag group containing `i` (`-i`, `-i.bak`, bundled `-ni`).
        if arg == "--in-place" or arg.startswith("--in-place="):
            return False
        if is_flag and not is_long_flag and "i" in arg[1:]:
            return False

        # A script token is either the value of -e/--expression, or the first
        # bare (non-flag) argument. Inspect it for the `e` command.
        if expects_script or not is_flag:
            if _sed_script_executes(arg):
                return False
            expects_script = False
        if arg in ("-e", "--expression", "-f", "--file"):
            expects_script = True
    return True


def _sed_script_executes(script: str) -> bool:
    """True when a sed script token uses the `e` (execute shell) command."""
    stripped = script.strip()
    # A bare `e` command, or an `s///e` substitution flag.
    if stripped == "e" or stripped.startswith("e "):
        return True
    # s/.../.../<flags> where flags include `e`. Be conservative: look for an
    # `e` among the trailing flags of a substitution.
    if stripped.startswith("s") and len(stripped) > 1:
        delim = stripped[1]
        parts = stripped.split(delim)
        if len(parts) >= 4 and "e" in parts[3]:
            return True
    return False


def classify_command(ctx: CommandContext) -> CommandClass:
    cmd = ctx.base_command
    if not cmd:
        return CommandClass.UNKNOWN

    if cmd in _DANGEROUS_COMMANDS:
        return CommandClass.DANGEROUS

    if cmd == "git":
        return CommandClass.UNKNOWN

    # Destructive commands are never trusted on base name alone; ASK (which the
    # Auto classifier then evaluates in auto mode).
    if cmd in _DESTRUCTIVE_COMMANDS:
        return CommandClass.UNKNOWN

    if cmd == "find":
        return (
            CommandClass.READ_ONLY if _find_is_read_only(ctx) else CommandClass.UNKNOWN
        )

    if cmd == "sed":
        # Read-only sed (no in-place / no `e`) is a safe stream filter; an
        # editing or executing sed falls through to the classifier.
        return (
            CommandClass.READ_ONLY if _sed_is_read_only(ctx) else CommandClass.UNKNOWN
        )

    if cmd in _READ_ONLY_COMMANDS:
        return CommandClass.READ_ONLY

    if cmd in _WRITE_LIMITED_COMMANDS:
        return CommandClass.WRITE_LIMITED

    return CommandClass.UNKNOWN


def is_high_risk(ctx: CommandContext, command_class: CommandClass) -> bool:
    if command_class == CommandClass.DANGEROUS:
        return True

    return False
