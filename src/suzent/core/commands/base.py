"""Unified slash command registry — works across frontend, social, and all other surfaces."""

from dataclasses import dataclass, field
from typing import Callable, Awaitable, Dict, Any

# Handler signature: (ctx, cmd, args) -> str | None
# Return str  = command handled, use as response text (empty string = handler sent its own reply)
# Return None = not handled (fall through)
CommandHandler = Callable[["CommandContext", str, list], Awaitable[str | None]]


@dataclass
class CommandMeta:
    name: str  # primary name without slash, e.g. "compact"
    aliases: list[str]  # all registered aliases with slash, e.g. ["/compact"]
    description: str
    usage: str  # e.g. "/compact [focus text]"
    surfaces: list[str] = field(default_factory=lambda: ["all"])
    # "all" | "social" | "frontend"


@dataclass
class CommandContext:
    chat_id: str
    user_id: str
    # Social-specific — None when called from frontend / API
    platform: str | None = None
    sender_id: str | None = None
    channel_manager: Any | None = None


_REGISTRY: Dict[str, CommandHandler] = {}
_META: list[CommandMeta] = []


def register_command(
    aliases: list[str],
    description: str = "",
    usage: str = "",
    surfaces: list[str] | None = None,
):
    def decorator(fn: CommandHandler):
        meta = CommandMeta(
            name=aliases[0].lstrip("/"),
            aliases=aliases,
            description=description,
            usage=usage or aliases[0],
            surfaces=surfaces or ["all"],
        )
        _META.append(meta)
        for alias in aliases:
            _REGISTRY[alias.lower()] = fn
        return fn

    return decorator


def list_commands(surface: str | None = None) -> list[CommandMeta]:
    """Return registered commands, optionally filtered by surface."""
    if surface is None:
        return list(_META)
    return [m for m in _META if "all" in m.surfaces or surface in m.surfaces]


async def dispatch(ctx: CommandContext, message: str) -> str | None:
    """
    Parse and execute a slash command.
    Returns response text if handled, None if not a command or unrecognised.
    """
    content = message.strip()
    if not content.startswith("/"):
        return None

    parts = content.split()
    cmd_name = parts[0].lower()
    args = parts[1:]

    handler = _REGISTRY.get(cmd_name)
    if handler is None:
        return None

    return await handler(ctx, cmd_name, args)
