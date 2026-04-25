"""
/model command — view or change the model for the current chat.

Usage:
  /model          — show the current model
  /model <id>     — switch to a specific model ID
  /model ls       — list all enabled models
"""

import typer
from suzent.core.commands.base import register_command, CommandContext


@register_command(
    aliases=["/model"],
    description="View or change the active model for this chat",
    usage="/model [ls | <model-id>]",
    surfaces=["cli", "frontend", "social"],
    category="session",
    options={
        "ls": "List all enabled models",
        "<model-id>": "Switch to the specified model",
    },
)
def handle_model(
    ctx: typer.Context,
    target: str = typer.Argument(None, help="Model ID to switch to, or 'ls' to list"),
):
    async def _impl():
        cmd_ctx: CommandContext = ctx.obj
        from suzent.database import get_database
        from suzent.core.providers.helpers import get_enabled_models_from_db

        db = get_database()
        models = get_enabled_models_from_db()

        # Read current model: explicit override > primary role > "(not set)"
        chat = db.get_chat(cmd_ctx.chat_id)
        current_model = (chat.config or {}).get("model") if chat else None
        if not current_model:
            try:
                from suzent.core.role_router import get_role_router

                current_model = get_role_router().get_model_id("primary") or "(not set)"
            except Exception:
                current_model = "(not set)"

        # Social channels: show interactive options (buttons if supported, text otherwise)
        if (
            (target is None or target.lower() == "ls")
            and cmd_ctx.channel_manager
            and cmd_ctx.platform
        ):
            channel = cmd_ctx.channel_manager.channels.get(cmd_ctx.platform)
            if channel:
                if not models:
                    return "No models enabled. Configure providers in Settings."
                sender_id = cmd_ctx.sender_id or cmd_ctx.chat_id
                options = [
                    (
                        f"• {m.split('/', 1)[-1]}"
                        if m == current_model
                        else m.split("/", 1)[-1],
                        f"/model {m}",
                    )
                    for m in models
                ]
                await channel.send_options(
                    sender_id,
                    f"Current model: `{current_model}`\nSelect a model:",
                    options,
                )
                return ""

        if target is None:
            return f"Current model: `{current_model}`"

        if target.lower() == "ls":
            if not models:
                return "No models enabled. Configure providers in Settings."
            lines = ["Enabled models:"]
            for m in models:
                marker = " ◀" if m == current_model else ""
                lines.append(f"  {m}{marker}")
            return "\n".join(lines)

        # Switch model — text path (CLI, frontend, social non-Telegram)
        if models and target not in models:
            matches = [m for m in models if target.lower() in m.lower()]
            if len(matches) == 1:
                target_resolved = matches[0]
            elif len(matches) > 1:
                suggestions = "\n".join(f"  {m}" for m in matches[:8])
                return f"Ambiguous: '{target}' matches {len(matches)} models:\n{suggestions}"
            else:
                return (
                    f"Model '{target}' is not in the enabled list. "
                    f"Use /model ls to see available models."
                )
        else:
            target_resolved = target

        if not chat:
            return "No active chat found. Send a message first."

        new_config = dict(chat.config or {})
        new_config["model"] = target_resolved
        db.update_chat(cmd_ctx.chat_id, config=new_config)

        return f"Model switched to `{target_resolved}`"

    return _impl
