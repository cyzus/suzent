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

        # Telegram: show interactive keyboard for /model and /model ls
        if (
            cmd_ctx.platform == "telegram"
            and cmd_ctx.channel_manager
            and (target is None or target.lower() == "ls")
        ):
            tg = cmd_ctx.channel_manager.channels.get("telegram")
            if not models:
                return "No models enabled. Configure providers in Settings."
            if tg:
                sender_id = cmd_ctx.sender_id or cmd_ctx.chat_id
                buttons = _build_model_keyboard(models, sender_id, current_model)
                await tg.send_keyboard(
                    sender_id,
                    f"Current model: <code>{current_model}</code>\nSelect a model:",
                    buttons,
                )
                return ""  # empty string = handled, no extra text response

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


def _build_model_keyboard(
    models: list[str],
    sender_id: str,
    current_model: str,
    page: int = 0,
    page_size: int = 16,
) -> list[list[tuple[str, str]]]:
    """Build a 2-column inline keyboard for model selection.

    Each button label shows the part after the provider prefix (e.g. 'gpt-4.1'
    from 'openai/gpt-4.1'), with a marker on the current model.
    Callback data: ms:{sender_id}:{global_model_index}
    """
    start = page * page_size
    page_models = models[start : start + page_size]

    rows: list[list[tuple[str, str]]] = []
    for i in range(0, len(page_models), 2):
        row = []
        for j in range(2):
            if i + j >= len(page_models):
                break
            global_idx = start + i + j
            m = page_models[i + j]
            short = m.split("/", 1)[-1]
            label = f"• {short}" if m == current_model else short
            row.append((label, f"ms:{sender_id}:{global_idx}"))
        rows.append(row)

    # Pagination row
    total_pages = (len(models) + page_size - 1) // page_size
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(("◀ Prev", f"mp:{sender_id}:{page - 1}"))
        if page < total_pages - 1:
            nav.append(("Next ▶", f"mp:{sender_id}:{page + 1}"))
        if nav:
            rows.append(nav)

    return rows
