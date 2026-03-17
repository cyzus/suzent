"""Unified slash commands — work across frontend, social, and all other surfaces."""

from suzent.core.commands import approve, compact, help  # noqa: F401 — registers all commands
from suzent.core.commands.base import dispatch, CommandContext

__all__ = ["dispatch", "CommandContext"]
