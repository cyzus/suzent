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


async def _compact_stream(chat_id: str, focus: str | None):
    from suzent.config import CONFIG
    from suzent.core.commands.base import CommandContext, dispatch

    # Note: the context-window usage panel is refreshed centrally by
    # emit_compaction_event (stage="complete") in the /compact command — it persists
    # chat.context_usage and broadcasts a bus payload carrying the recomputed usage,
    # so every compaction surface updates identically. This route only relays the
    # human-readable result string.
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
            yield _sse("compaction_complete", {"skipped": False, "message": result})
    except Exception as e:
        logger.error(f"Compact route failed for {chat_id}: {e}")
        yield _sse("compaction_error", {"message": str(e)})
