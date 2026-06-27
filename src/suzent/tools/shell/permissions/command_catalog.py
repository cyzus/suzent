from __future__ import annotations

from typing import Literal

from .policy_models import CommandContext

type PathOperation = Literal["read", "write", "cwd", "delete"]

READ_ONLY_COMMANDS = frozenset(
    {
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
)

# Commands that create or copy but do not destroy existing data. These stay
# auto-allowable under accept-edits / auto mode, matching the workspace
# file-write fast path.
WRITE_LIMITED_COMMANDS = frozenset(
    {
        "mkdir",
        "touch",
        "cp",
    }
)

# Destructive or in-place-rewriting commands. Even inside the workspace these
# are not auto-allowed by mode alone: they fall through to ASK (and therefore to
# the Auto classifier in auto mode) instead of being trusted on base name.
DESTRUCTIVE_COMMANDS = frozenset(
    {
        "rm",
        "rmdir",
        "mv",
    }
)

DANGEROUS_COMMANDS = frozenset(
    {
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
)

COMMAND_PATH_OPERATIONS: dict[str, PathOperation] = {
    **dict.fromkeys(READ_ONLY_COMMANDS, "read"),
    **dict.fromkeys(WRITE_LIMITED_COMMANDS, "write"),
    # rm/rmdir destroy data. mv is also classified destructive (so it is never
    # trusted on base name alone), but its path use is a write to the
    # destination rather than a delete.
    "rm": "delete",
    "rmdir": "delete",
    "mv": "write",
    "cd": "cwd",
    "find": "read",
}

# find flags that delete or run other programs, making the invocation mutating
# or code-executing rather than read-only.
FIND_MUTATING_FLAGS = frozenset(
    {
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
)


def find_is_read_only(ctx: CommandContext) -> bool:
    """`find` only reads unless it is told to delete or execute."""
    return not any(arg in FIND_MUTATING_FLAGS for arg in ctx.args)


def sed_is_read_only(ctx: CommandContext) -> bool:
    """`sed` is read-only unless it edits in place or runs the `e` command."""
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
            if sed_script_executes(arg):
                return False
            expects_script = False
        if arg in ("-e", "--expression", "-f", "--file"):
            expects_script = True
    return True


def sed_script_executes(script: str) -> bool:
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


def path_operation_for(ctx: CommandContext) -> PathOperation | None:
    if ctx.base_command == "sed":
        return "read" if sed_is_read_only(ctx) else "write"
    return COMMAND_PATH_OPERATIONS.get(ctx.base_command)
