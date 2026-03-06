"""Social /steer command — redirect the agent mid-response."""

from suzent.channels.base import UnifiedMessage
from suzent.social.commands.base import register_command


@register_command(["/steer", "/redirect"])
async def handle_steer(message: UnifiedMessage, channel_manager, args: list) -> bool:
    """
    Redirect the agent mid-response.

    This command is intercepted early by the SocialBrain's _route_message
    which detects /steer and treats it as a steer signal. The actual
    processing happens in _handle_message with is_steer=True.

    If no active run exists, it falls through to normal processing.
    We return False here so the message is NOT consumed by the command
    dispatcher — instead it flows through _route_message's steer logic.
    """
    # Don't consume: let _route_message handle it as a steer
    return False
