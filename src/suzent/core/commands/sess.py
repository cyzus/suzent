"""
/sess command — session switching for social channels.

Commands:
  /sess ls          — list all chats with IDs and titles
  /sess switch <id> — switch active chat for this user/channel
  /sess new [title] — create a new chat and switch to it
  /sess info        — show current active chat info
  /sess reset       — go back to the default session
"""

import typer
from suzent.channels.session_binding import clear_binding, get_binding, set_binding
from suzent.core.commands.base import register_command, CommandContext
from suzent.core.focal_agent import FOCAL_CHAT_ID, FOCAL_TITLE
from suzent.database import get_database


def get_active_chat_id(binding_key: str, default_chat_id: str) -> str:
    """Return the chat a conversation is bound to, or its default chat."""
    return get_binding(binding_key) or default_chat_id


def set_active_chat_id(binding_key: str, chat_id: str) -> None:
    """Bind a conversation to a specific chat_id."""
    set_binding(binding_key, chat_id)


def clear_active_chat_id(binding_key: str) -> None:
    """Remove a conversation's binding so it falls back to its default chat."""
    clear_binding(binding_key)


def _binding_key(ctx: CommandContext) -> str:
    return ctx.binding_key or ctx.sender_id or ctx.chat_id


def _default_label(ctx: CommandContext) -> str:
    if ctx.chat_id == FOCAL_CHAT_ID:
        return FOCAL_TITLE
    return f"default chat ({ctx.chat_id[-8:]})"


@register_command(
    aliases=["/sess"],
    description="Manage sessions: ls, switch <id>, new [title], info, reset",
    usage="/sess <ls|switch|new|info|reset> [args]",
    surfaces=["social"],
    category="session",
    options={
        "ls": "List recent sessions",
        "switch": "Switch to an existing session",
        "new": "Create a new session",
        "info": "Show current session info",
        "reset": "Go back to the default session",
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
        elif sub_lower == "reset":
            clear_active_chat_id(_binding_key(cmd_ctx))
            return f"✅ Back to {_default_label(cmd_ctx)}"
        else:
            return (
                "Unknown subcommand. Usage:\n"
                "  /sess ls — list sessions\n"
                "  /sess switch <id> — switch session\n"
                "  /sess new [title] — create new session\n"
                "  /sess info — current session info\n"
                "  /sess reset — back to the default session"
            )

    return _impl


@register_command(
    aliases=["/new"],
    description="Create a new session and switch to it",
    usage="/new [title]",
    surfaces=["social"],
    category="session",
)
def new_command(
    ctx: typer.Context,
    title: list[str] = typer.Argument(None, help="Optional session title"),
):
    """Short form of ``/sess new [title]``."""

    async def _impl():
        return await _cmd_new(ctx.obj, title)

    return _impl


async def _cmd_ls(ctx: CommandContext) -> str:
    db = get_database()
    chats = db.list_chats(limit=20)
    if not chats:
        return "No sessions found."

    sender_id = ctx.sender_id or ctx.chat_id
    active_id = get_active_chat_id(_binding_key(ctx), ctx.chat_id)

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

    set_active_chat_id(_binding_key(ctx), chat_id)
    return f"✅ Switched to: [{chat_id[-8:]}] {title}"


async def _cmd_new(ctx: CommandContext, args: list) -> str:
    title = " ".join(args) if args else "New Session"
    db = get_database()
    chat_id = db.create_chat(title=title, config={"platform": ctx.platform or "social"})
    set_active_chat_id(_binding_key(ctx), chat_id)
    return f"✅ Created and switched to: [{chat_id[-8:]}] {title}"


async def _cmd_info(ctx: CommandContext) -> str:
    key = _binding_key(ctx)
    active_id = get_binding(key)

    if not active_id:
        return f"Current session: {_default_label(ctx)}"

    db = get_database()
    chat = db.get_chat(active_id)
    if not chat:
        clear_active_chat_id(key)
        return "Active session no longer exists. Reverted to default."

    msg_count = len(chat.messages or [])
    wd = db.resolve_chat_working_directory(chat) or "(none)"
    return (
        f"📁 Active session:\n"
        f"  ID: {active_id[-8:]}\n"
        f"  Title: {chat.title}\n"
        f"  Messages: {msg_count}\n"
        f"  Working dir: {wd}"
    )
