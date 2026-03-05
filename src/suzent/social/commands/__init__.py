"""Social channel slash commands registry and dispatcher."""

# Import all command modules to register them
from suzent.social.commands import approve, help  # noqa: F401
from suzent.social.commands.base import dispatch_command

__all__ = ["dispatch_command"]
