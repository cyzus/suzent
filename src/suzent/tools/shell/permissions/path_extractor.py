from __future__ import annotations

from .policy_models import CommandContext, PathUse


def _is_flag(token: str) -> bool:
    return token.startswith("-")


def _positional_args(args: list[str]) -> list[str]:
    out: list[str] = []
    after_double_dash = False
    for arg in args:
        if arg == "--":
            after_double_dash = True
            continue
        if not after_double_dash and _is_flag(arg):
            continue
        out.append(arg)
    return out


def extract_path_uses(ctx: CommandContext) -> list[PathUse]:
    cmd = ctx.base_command
    args = _positional_args(ctx.args)
    uses: list[PathUse] = []

    if cmd == "cd":
        if args:
            uses.append(PathUse(path=args[0], operation="cwd"))
        return uses

    if cmd in {"cat", "head", "tail", "ls", "find", "grep", "rg", "stat", "file"}:
        for item in args:
            uses.append(PathUse(path=item, operation="read"))

    if cmd in {"mkdir", "touch", "cp", "mv", "sed"}:
        for item in args:
            uses.append(PathUse(path=item, operation="write"))

    if cmd in {"rm", "rmdir"}:
        for item in args:
            uses.append(PathUse(path=item, operation="delete"))

    for redir in ctx.redirections:
        uses.append(PathUse(path=redir, operation="write"))

    return uses
