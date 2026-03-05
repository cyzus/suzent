"""Help command module."""

from suzent.social.commands.base import register_command


@register_command(["/help", "/h", "/?"])
async def handle_help(message, channel_manager, args):
    """Show available commands."""
    await channel_manager.send_message(
        message.platform,
        message.sender_id,
        "🤖 **Suzent Commands**\n"
        "  `/y [id]` — Approve (aliases: `/yes`, `/allow`)\n"
        "  `/n [id]` — Deny (aliases: `/no`, `/reject`)\n"
        "  `/help` — Show this message\n\n"
        "*Hint: No ID needed if only 1 action is pending.*",
    )
    return True
