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
        cmd_ctx: CommandContext = ctx.obj
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

        if cmd_ctx and cmd_ctx.chat_id:
            from suzent.database import get_database
            from suzent.core.agent_serializer import deserialize_state
            from suzent.core.context_compressor import estimate_tokens
            from suzent.config import CONFIG
            from suzent.core.cost_tracker import get_cost_tracker

            db = get_database()
            chat = db.get_chat(cmd_ctx.chat_id)
            if chat:
                status.append("")
                status.append("**Session**")
                status.append(f"  Turns: {chat.turn_count}")

                if chat.agent_state:
                    state = deserialize_state(chat.agent_state)
                    if state:
                        model_id = state.get("model_id") or "unknown"
                        msg_history = state.get("message_history") or []
                        status.append(f"  Model: {model_id}")

                        budget = estimate_tokens(msg_history, CONFIG.max_context_tokens)
                        pct = budget.estimated_tokens / budget.limit * 100
                        bar_filled = int(pct / 5)
                        bar = "█" * bar_filled + "░" * (20 - bar_filled)
                        status.append("")
                        status.append("**Context**")
                        status.append(f"  [{bar}] {pct:.1f}%")
                        status.append(
                            f"  ~{budget.estimated_tokens:,} / {budget.limit:,} tokens (est.)"
                        )

                tracker = get_cost_tracker()
                cost = await tracker.get_chat_cost(cmd_ctx.chat_id)
                total_in = cost.get("total_input_tokens", 0)
                total_out = cost.get("total_output_tokens", 0)
                cache_write = cost.get("total_cache_write_tokens", 0)
                cache_read = cost.get("total_cache_read_tokens", 0)
                total_cost = cost.get("total_cost_usd", 0.0)
                if total_in or total_out:
                    status.append("")
                    status.append("**Usage (this chat)**")
                    status.append(f"  Input:  {total_in:,} tokens")
                    status.append(f"  Output: {total_out:,} tokens")
                    if cache_write or cache_read:
                        status.append(f"  Cache write: {cache_write:,} tokens")
                        status.append(f"  Cache read:  {cache_read:,} tokens")
                    if total_cost > 0:
                        status.append(f"  Cost:   ${total_cost:.4f}")

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
