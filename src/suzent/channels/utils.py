"""
Shared utilities for social channel operations.

Consolidates helpers that were duplicated across social_brain, approve command,
and social_message_tool.
"""

from suzent.channels.base import UnifiedMessage


def extract_target_id(message: UnifiedMessage) -> str:
    """Extract the target (thread/group/DM) ID from a unified message's chat ID.

    The chat ID format is ``"platform:target_id"``.
    """
    return message.get_chat_id().split(":", 1)[1]


def get_channel_manager():
    """Resolve the active ChannelManager from the SocialBrain singleton.

    Returns None if no social brain is running.
    """
    from suzent.core.social_brain import get_active_social_brain

    brain = get_active_social_brain()
    return brain.channel_manager if brain else None
