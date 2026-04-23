import typer
from suzent.core.commands.base import register_command, CommandContext


@register_command(
    ["/help", "/h", "/?"],
    description="Show available commands",
    usage="/help",
    category="system",
)
def handle_help(ctx: typer.Context):
    """Show available commands."""

    async def _impl():
        cmd_ctx: CommandContext = ctx.obj
        from suzent.core.commands.base import list_commands

        cmds = list_commands(surface=cmd_ctx.surface)
        lines = ["🤖 **Suzent Commands**"]
        for c in cmds:
            lines.append(f"  `{c.usage}` — {c.description}")
        help_text = "\n".join(lines)

        if cmd_ctx.channel_manager and cmd_ctx.platform and cmd_ctx.sender_id:
            await cmd_ctx.channel_manager.send_message(
                cmd_ctx.platform, cmd_ctx.sender_id, help_text
            )
            return ""  # already sent directly
        return help_text

    return _impl
