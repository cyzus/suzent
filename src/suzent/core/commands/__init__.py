"""Unified slash commands — work across frontend, social, and all other surfaces."""

from suzent.core.commands.base import dispatch, list_commands, CommandContext
from suzent.core.commands.compact import handle_compact
from suzent.core.commands.approve import handle_approve, handle_deny
from suzent.core.commands.help import handle_help
from suzent.core.commands.model import handle_model
from suzent.core.commands.sess import sess_command
from suzent.core.commands.system import handle_status, handle_clear
from suzent.core.commands.node import handle_node

__all__ = [
    "dispatch",
    "list_commands",
    "CommandContext",
    "handle_compact",
    "handle_approve",
    "handle_deny",
    "handle_help",
    "handle_model",
    "sess_command",
    "handle_status",
    "handle_clear",
    "handle_node",
]
