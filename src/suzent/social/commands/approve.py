"""Approval command handler."""

from suzent.social.commands.base import register_command

_APPROVE = {"/approve", "/y", "/yes", "/allow", "/ya"}
_DENY = {"/n", "/no", "/deny", "/reject", "/na"}
_REMEMBER = {"/ya", "/na"}


@register_command([*_APPROVE, *_DENY])
async def handle_approval(message, channel_manager, args):
    """Handle tool approval resolution with friendly UX."""
    from suzent.core.social_brain import get_active_social_brain

    brain = get_active_social_brain()
    if not brain:
        return False

    trigger = message.content.split()[0].lower()
    approved = trigger in _APPROVE
    remember = trigger in _REMEMBER

    target_id = message.get_chat_id().split(":", 1)[1]
    await brain.handle_approval_response(
        message.platform,
        target_id,
        approved,
        sender_id=message.sender_id,
        remember=remember,
    )
    return True
