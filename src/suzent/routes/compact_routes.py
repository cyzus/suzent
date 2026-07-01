"""
Compact route: POST /chat/compact

Thin SSE wrapper around the universal /compact core command.
"""

import json

from starlette.requests import Request
from starlette.responses import StreamingResponse, JSONResponse

from suzent.logger import get_logger

logger = get_logger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event, **data})}\n\n"


async def compact_chat(request: Request) -> StreamingResponse:
    """
    Compact the context for a chat, streaming progress via SSE.

    Request body:
        chat_id (str): required
        focus   (str): optional instructions to guide the summary
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    chat_id = body.get("chat_id")
    focus = body.get("focus", "").strip() or None

    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)

    return StreamingResponse(
        _compact_stream(chat_id, focus),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _post_compaction_tokens(chat_id: str) -> dict:
    """Recompute the context-window totals from the (now compacted) agent_state.

    The frontend usage panel is fed by provider-reported usage from the last model
    request, which /compact never touches — so it stays stale after a manual compact
    until the next turn. We return the fresh estimate here so the client can update
    the panel immediately. Cache/cumulative fields are reset (unknown until the next
    real request repopulates them)."""
    try:
        from suzent.config import CONFIG
        from suzent.database import get_database
        from suzent.core.agent_serializer import deserialize_state
        from suzent.core.context_compressor import estimate_tokens

        chat = get_database().get_chat(chat_id)
        if not chat or not chat.agent_state:
            return {}
        state = deserialize_state(chat.agent_state)
        messages = (state or {}).get("message_history") or []
        tokens = estimate_tokens(messages, CONFIG.max_context_tokens).estimated_tokens
        return {
            "usage": {
                "input_tokens": tokens,
                "output_tokens": 0,
                "total_tokens": tokens,
                "context_tokens": tokens,
                "cache_write_tokens": 0,
                "cache_read_tokens": 0,
                "requests": 0,
                "details": {},
            }
        }
    except Exception as e:
        logger.debug(f"Failed to recompute post-compaction tokens for {chat_id}: {e}")
        return {}


async def _compact_stream(chat_id: str, focus: str | None):
    from suzent.config import CONFIG
    from suzent.core.commands.base import CommandContext, dispatch

    try:
        yield _sse(
            "compaction_progress",
            {"stage": "summarizing", "message": "Compacting context..."},
        )
        ctx = CommandContext(chat_id=chat_id, user_id=CONFIG.user_id, surface="manual")
        command_str = f"/compact -- {focus}" if focus else "/compact"
        result = await dispatch(ctx, command_str)
        if result is None:
            yield _sse(
                "compaction_error",
                {"message": "Command dispatch failed or returned no result."},
            )
        else:
            yield _sse(
                "compaction_complete",
                {
                    "skipped": False,
                    "message": result,
                    **_post_compaction_tokens(chat_id),
                },
            )
    except Exception as e:
        logger.error(f"Compact route failed for {chat_id}: {e}")
        yield _sse("compaction_error", {"message": str(e)})
