import typer
from suzent.core.commands.base import register_command, CommandContext
from suzent.logger import get_logger

logger = get_logger(__name__)


@register_command(
    ["/compact"],
    description="Summarise and compress conversation context",
    usage="/compact [focus text]",
    category="tools",
)
def handle_compact(
    ctx: typer.Context,
    focus: list[str] = typer.Argument(
        None, help="Optional text to focus the compression on"
    ),
):
    """Summarise and compress the agent's message history. Always runs (manual override)."""

    async def _impl():
        from suzent.database import get_database
        from suzent.core.agent_serializer import serialize_state, deserialize_state
        from suzent.core.context_compressor import (
            ContextCompressor,
            emit_compaction_event,
            estimate_tokens,
        )
        from suzent.config import CONFIG

        cmd_ctx: CommandContext = ctx.obj
        focus_text = " ".join(focus).strip() if focus else None
        event_source = "manual" if cmd_ctx.surface == "manual" else "slash"

        db = get_database()
        chat = db.get_chat(cmd_ctx.chat_id)
        if not chat or not chat.agent_state:
            emit_compaction_event(
                chat_id=cmd_ctx.chat_id,
                stage="skipped",
                source=event_source,
                message="No conversation history to compact.",
                persist_result=event_source == "manual",
            )
            return "ℹ No conversation history to compact."

        state = deserialize_state(chat.agent_state)
        if not state or not state.get("message_history"):
            emit_compaction_event(
                chat_id=cmd_ctx.chat_id,
                stage="skipped",
                source=event_source,
                message="No message history found.",
                persist_result=event_source == "manual",
            )
            return "ℹ No message history found."

        messages = state["message_history"]
        model_id = state.get("model_id")
        tool_names = state.get("tool_names", [])

        tokens_before = estimate_tokens(
            messages, CONFIG.max_context_tokens
        ).estimated_tokens
        messages_before = len(messages)

        compressor = ContextCompressor(chat_id=cmd_ctx.chat_id, user_id=cmd_ctx.user_id)
        emit_compaction_event(
            chat_id=cmd_ctx.chat_id,
            stage="start",
            source=event_source,
            messages_before=messages_before,
            tokens_before=tokens_before,
        )
        try:
            compressed = await compressor._perform_compression(
                messages, focus=focus_text
            )
        except Exception as e:
            emit_compaction_event(
                chat_id=cmd_ctx.chat_id,
                stage="error",
                source=event_source,
                messages_before=messages_before,
                tokens_before=tokens_before,
                message=str(e),
                persist_result=event_source == "manual",
            )
            raise

        agent_state_bytes = serialize_state(
            compressed, model_id=model_id, tool_names=tool_names
        )
        db.update_chat(cmd_ctx.chat_id, agent_state=agent_state_bytes)

        tokens_after = estimate_tokens(
            compressed, CONFIG.max_context_tokens
        ).estimated_tokens
        emit_compaction_event(
            chat_id=cmd_ctx.chat_id,
            stage="complete",
            source=event_source,
            messages_before=messages_before,
            messages_after=len(compressed),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            persist_result=event_source == "manual",
        )
        before_k = round(tokens_before / 1000)
        after_k = round(tokens_after / 1000)

        logger.info(
            f"[/compact] {cmd_ctx.chat_id}: {messages_before}→{len(compressed)} msgs, ~{before_k}k→~{after_k}k tokens"
        )
        return f"✓ Context compacted: ~{before_k}k → ~{after_k}k tokens ({messages_before} → {len(compressed)} messages)"

    return _impl
