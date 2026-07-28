import typer

from suzent.core.commands.base import CommandContext, register_command


@register_command(
    ["/fork"],
    description="Create an independent copy of the current conversation",
    usage="/fork",
    category="session",
)
def handle_fork(ctx: typer.Context):
    async def _impl() -> str:
        from suzent.core.fork import fork_chat

        cmd_ctx: CommandContext = ctx.obj
        new_chat_id, _ = fork_chat(cmd_ctx.chat_id)
        if cmd_ctx.surface == "social":
            from suzent.core.commands.sess import set_active_chat_id

            set_active_chat_id(cmd_ctx.sender_id or cmd_ctx.chat_id, new_chat_id)
        return f"✓ Forked conversation to [{new_chat_id[-8:]}] ({new_chat_id})."

    return _impl
