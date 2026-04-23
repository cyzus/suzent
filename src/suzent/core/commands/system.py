import typer
from suzent.core.commands.base import register_command, CommandContext


@register_command(
    ["/status", "/stat"],
    description="Show server status, memory usage, and background health",
    usage="/status",
    surfaces=["cli", "frontend", "social"],
    category="session",
)
def handle_status(ctx: typer.Context):
    async def _impl():
        # cmd_ctx: CommandContext = ctx.obj
        import os
        import platform
        import psutil

        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / 1024 / 1024

        status = [
            "🟢 **Suzent Status**",
            f"  System: {platform.system()} {platform.release()}",
            f"  Memory: {mem_mb:.1f} MB",
            f"  Python: {platform.python_version()}",
        ]
        return "\n".join(status)

    return _impl


@register_command(
    ["/clear", "/reset"],
    description="Truncate the current conversation history",
    usage="/clear",
    surfaces=["cli", "frontend"],
    category="session",
)
def handle_clear(ctx: typer.Context):
    async def _impl():
        cmd_ctx: CommandContext = ctx.obj
        from suzent.database import get_database

        db = get_database()
        chat = db.get_chat(cmd_ctx.chat_id)
        if not chat:
            return "No active session to clear."

        db.update_chat(cmd_ctx.chat_id, messages=[])
        return "🧹 Conversation history cleared. New messages will start with an empty context."

    return _impl
