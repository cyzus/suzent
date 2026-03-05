"""Modular command registry for social channels."""

from typing import Dict, Callable, Awaitable

from suzent.channels.base import UnifiedMessage

# Type for command handlers
CommandHandler = Callable[[UnifiedMessage, object, list], Awaitable[bool]]

_REGISTRY: Dict[str, CommandHandler] = {}


def register_command(aliases: list[str]):
    def decorator(fn: CommandHandler):
        for alias in aliases:
            _REGISTRY[alias.lower()] = fn
        return fn

    return decorator


async def dispatch_command(message: UnifiedMessage, channel_manager) -> bool:
    """
    Parse and execute a slash command if one is matched.
    Returns True if a command was handled.
    """
    content = message.content.strip()
    if not content.startswith("/"):
        return False

    parts = content.split()
    cmd_name = parts[0].lower()
    args = parts[1:]

    handler = _REGISTRY.get(cmd_name)
    if handler:
        return await handler(message, channel_manager, args)
    return False
