"""
/sess command — session switching for social channels.

Commands:
  /sess ls          — list all chats with IDs and titles
  /sess switch <id> — switch active chat for this user/channel
  /sess new [title] — create a new chat and switch to it
  /sess info        — show current active chat info
"""

import typer
from suzent.core.commands.base import register_command, CommandContext
from suzent.database import get_database

# In-memory mapping: sender_id -> active_chat_id
# Persists for the duration of the server process.
_active_chats: dict[str, str] = {}
_lock_map: dict[str, object] = {}  # per-sender asyncio.Lock, created lazily


def get_active_chat_id(sender_id: str, default_chat_id: str) -> str:
    """Return the active chat_id for a sender, defaulting to their social chat."""
    return _active_chats.get(sender_id, default_chat_id)


def set_active_chat_id(sender_id: str, chat_id: str) -> None:
    """Bind a sender to a specific chat_id."""
    _active_chats[sender_id] = chat_id


def clear_active_chat_id(sender_id: str) -> None:
    """Remove a sender's chat binding (falls back to default social chat)."""
    _active_chats.pop(sender_id, None)


@register_command(
    aliases=["/sess"],
    description="Manage sessions: ls, switch <id>, new [title], info",
    usage="/sess <ls|switch|new|info> [args]",
    surfaces=["social"],
    category="session",
    options={
        "ls": "List recent sessions",
        "switch": "Switch to an existing session",
        "new": "Create a new session",
        "info": "Show current session info",
    },
)
def sess_command(
    ctx: typer.Context,
    sub: str = typer.Argument("info", help="Subcommand: ls, switch, new, info"),
    args: list[str] = typer.Argument(None, help="Arguments for the subcommand"),
):
    async def _impl():
        cmd_ctx: CommandContext = ctx.obj
        sub_lower = sub.lower()

        if sub_lower == "ls":
            return await _cmd_ls(cmd_ctx)
        elif sub_lower == "switch":
            return await _cmd_switch(cmd_ctx, args)
        elif sub_lower == "new":
            return await _cmd_new(cmd_ctx, args)
        elif sub_lower == "info":
            return await _cmd_info(cmd_ctx)
        else:
            return (
                "Unknown subcommand. Usage:\n"
                "  /sess ls — list sessions\n"
                "  /sess switch <id> — switch session\n"
                "  /sess new [title] — create new session\n"
                "  /sess info — current session info"
            )

    return _impl


async def _cmd_ls(ctx: CommandContext) -> str:
    db = get_database()
    chats = db.list_chats(limit=20)
    if not chats:
        return "No sessions found."

    sender_id = ctx.sender_id or ctx.chat_id
    active_id = _active_chats.get(sender_id)

    if ctx.channel_manager and ctx.platform:
        channel = ctx.channel_manager.channels.get(ctx.platform)
        if channel:
            options = []
            for chat in chats:
                short_id = chat.id[-8:] if len(chat.id) > 8 else chat.id
                marker = " ◀" if chat.id == active_id else ""
                label = f"{chat.title}{marker} [{short_id}]"
                options.append((label, f"/sess switch {chat.id}"))
            await channel.send_options(
                sender_id,
                "📋 Sessions (tap to switch):",
                options,
                columns=1,
            )
            return ""

    lines = ["📋 Sessions (most recent first):"]
    for chat in chats:
        marker = " ◀ active" if chat.id == active_id else ""
        short_id = chat.id[-8:] if len(chat.id) > 8 else chat.id
        lines.append(f"  [{short_id}] {chat.title}{marker}")
    lines.append("\nUse /sess switch <id> to switch.")
    return "\n".join(lines)


async def _cmd_switch(ctx: CommandContext, args: list) -> str:
    if not args:
        return "Usage: /sess switch <chat-id>"

    target_id = args[0]
    db = get_database()

    # Support partial ID matching (last N chars)
    chat = db.get_chat(target_id)
    if not chat:
        # Try suffix match
        all_chats = db.list_chats(limit=100)
        matches = [c for c in all_chats if c.id.endswith(target_id)]
        if len(matches) == 1:
            chat_id = matches[0].id
            title = matches[0].title
        elif len(matches) > 1:
            return f"Ambiguous ID '{target_id}' matches {len(matches)} sessions. Use a longer suffix."
        else:
            return f"No session found with ID '{target_id}'."
    else:
        chat_id = chat.id
        title = chat.title

    sender_id = ctx.sender_id or ctx.chat_id
    set_active_chat_id(sender_id, chat_id)
    return f"✅ Switched to: [{chat_id[-8:]}] {title}"


async def _cmd_new(ctx: CommandContext, args: list) -> str:
    title = " ".join(args) if args else "New Session"
    db = get_database()
    chat_id = db.create_chat(title=title, config={"platform": ctx.platform or "social"})
    sender_id = ctx.sender_id or ctx.chat_id
    set_active_chat_id(sender_id, chat_id)
    return f"✅ Created and switched to: [{chat_id[-8:]}] {title}"


async def _cmd_info(ctx: CommandContext) -> str:
    sender_id = ctx.sender_id or ctx.chat_id
    active_id = _active_chats.get(sender_id)

    if not active_id:
        return f"Current session: default social chat ({ctx.chat_id[-8:]})"

    db = get_database()
    chat = db.get_chat(active_id)
    if not chat:
        clear_active_chat_id(sender_id)
        return "Active session no longer exists. Reverted to default."

    msg_count = len(chat.messages or [])
    wd = chat.working_directory or "(none)"
    return (
        f"📁 Active session:\n"
        f"  ID: {active_id[-8:]}\n"
        f"  Title: {chat.title}\n"
        f"  Messages: {msg_count}\n"
        f"  Working dir: {wd}"
    )
