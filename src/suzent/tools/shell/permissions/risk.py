from __future__ import annotations

import shlex
from pathlib import PurePosixPath

from suzent.permissions.models import PermissionRisk

from .command_catalog import DANGEROUS_COMMANDS, DESTRUCTIVE_COMMANDS


_LOW_RISK_COMMANDS = frozenset(
    {"cd", "pwd", "echo", "ls", "cat", "head", "tail", "wc", "stat", "file"}
)
_GIT_READ_COMMANDS = frozenset({"status", "log", "diff"})
_GIT_READ_FLAGS = frozenset(
    {
        "--short",
        "--branch",
        "--porcelain",
        "--oneline",
        "--stat",
        "--name-only",
        "--name-status",
        "--no-pager",
        "-n",
    }
)


def assess_command_risk(command: str) -> PermissionRisk:
    """Estimate effects separately from the policy's approval requirement.

    This is deliberately a narrow low-risk recognizer, not a shell interpreter.
    Unknown syntax stays medium; it never changes whether approval is required.
    """
    if "$(" in command or "`" in command:
        return PermissionRisk.HIGH
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return PermissionRisk.MEDIUM

    segments: list[list[str]] = [[]]
    uncertain = "\n" in command or "\r" in command
    for token in tokens:
        if token in {"&&", "||", ";", "|", "\n"}:
            segments.append([])
        else:
            segments[-1].append(token)
        if any(char in token for char in "><"):
            uncertain = True
    for segment in segments:
        if not segment:
            uncertain = True
            continue
        name, *args = segment
        if PurePosixPath(name).name in DANGEROUS_COMMANDS | DESTRUCTIVE_COMMANDS:
            return PermissionRisk.HIGH
        if name == "git":
            if args and args[0] in {
                "reset",
                "clean",
                "push",
                "restore",
                "checkout",
                "rebase",
            }:
                return PermissionRisk.HIGH
            if not args or args[0] not in _GIT_READ_COMMANDS:
                uncertain = True
            elif any(
                arg.startswith("-") and arg not in _GIT_READ_FLAGS for arg in args[1:]
            ):
                uncertain = True
        elif name not in _LOW_RISK_COMMANDS:
            uncertain = True
    return PermissionRisk.MEDIUM if uncertain or not tokens else PermissionRisk.LOW
