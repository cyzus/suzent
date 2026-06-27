from __future__ import annotations

from .command_catalog import path_operation_for
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


def _sed_path_args(args: list[str]) -> list[str]:
    paths: list[str] = []
    expects_script = False
    seen_script = False
    after_double_dash = False

    for arg in args:
        if arg == "--" and not after_double_dash:
            after_double_dash = True
            continue

        if expects_script:
            expects_script = False
            seen_script = True
            continue

        if not after_double_dash and arg in {"-e", "--expression", "-f", "--file"}:
            expects_script = True
            continue

        if not after_double_dash and _is_flag(arg):
            continue

        if not seen_script:
            seen_script = True
            continue

        paths.append(arg)

    return paths


def extract_path_uses(ctx: CommandContext) -> list[PathUse]:
    operation = path_operation_for(ctx)
    uses: list[PathUse] = []

    if operation is None:
        return uses

    args = (
        _sed_path_args(ctx.args)
        if ctx.base_command == "sed"
        else _positional_args(ctx.args)
    )

    if operation == "cwd":
        if args:
            uses.append(PathUse(path=args[0], operation="cwd"))
        return uses

    for item in args:
        uses.append(PathUse(path=item, operation=operation))

    for redir in ctx.redirections:
        uses.append(PathUse(path=redir, operation="write"))

    return uses
