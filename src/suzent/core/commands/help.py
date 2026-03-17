"""Help command (/help, /h, /?)."""

from suzent.core.commands.base import register_command, CommandContext

_HELP_TEXT = (
    "🤖 **Suzent Commands**\n"
    "  `/compact [focus]` — Compress conversation context\n"
    "  `/y [id]` — Approve pending tool (aliases: `/yes`, `/allow`)\n"
    "  `/n [id]` — Deny pending tool (aliases: `/no`, `/reject`)\n"
    "  `/help` — Show this message"
)


@register_command(
    ["/help", "/h", "/?"],
    description="Show available commands",
    usage="/help",
)
async def handle_help(ctx: CommandContext, cmd: str, args: list) -> str:
    """Show available commands."""
    if ctx.channel_manager and ctx.platform and ctx.sender_id:
        await ctx.channel_manager.send_message(ctx.platform, ctx.sender_id, _HELP_TEXT)
        return ""  # already sent directly
    return _HELP_TEXT
