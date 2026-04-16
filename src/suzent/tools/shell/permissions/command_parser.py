from __future__ import annotations

import re
import shlex

from .policy_models import CommandContext

_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIR_TARGET_RE = re.compile(r"(?:^|\s)(?:\d?>>?|\d?<)\s*([^\s]+)")


def _tokenize(command: str) -> list[str]:
    text = command.strip()
    if not text:
        return []

    try:
        return shlex.split(text, posix=True)
    except Exception:
        return text.split()


def parse_command(command: str) -> CommandContext:
    text = command.strip()
    tokens = _tokenize(text)

    idx = 0
    while idx < len(tokens) and _ENV_ASSIGN_RE.match(tokens[idx]):
        idx += 1

    base_command = tokens[idx] if idx < len(tokens) else ""
    args = tokens[idx + 1 :] if idx + 1 <= len(tokens) else []

    has_control_operators = any(op in text for op in ("&&", "||", "|", ";", "$(", "`"))

    redirections = [m.group(1).strip("\"'") for m in _REDIR_TARGET_RE.finditer(text)]

    return CommandContext(
        raw=command,
        tokens=tokens,
        base_command=base_command.lower(),
        args=args,
        redirections=redirections,
        has_control_operators=has_control_operators,
    )
