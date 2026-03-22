"""
A2UI action route.

Handles user interactions from the canvas panel (button clicks, form submits).
Formats the action as a lightweight user message and delegates to ChatProcessor,
returning a standard SSE stream identical to /chat.
"""

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.logger import get_logger
from suzent.a2ui import pending as pending_questions

logger = get_logger(__name__)


async def a2ui_action(request: Request) -> StreamingResponse:
    """
    POST /canvas/{chat_id}/action

    Body:
        surface_id  str   – which surface the user interacted with
        action      str   – action name defined in the component (e.g. "book_table")
        context     dict  – data payload from the component (button context or form data)
        config      dict  – optional agent config override (same as /chat)

    Returns the same SSE stream as /chat so the frontend handles it identically.
    The action is formatted as a special user message:
        [canvas: {action}] {json.dumps(context)}
    """
    chat_id = request.path_params.get("chat_id")
    if not chat_id:
        return JSONResponse({"error": "chat_id required"}, status_code=400)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    surface_id = data.get("surface_id", "")
    action = (data.get("action") or "submit").strip()
    context = data.get("context", {})
    config = data.get("config", {})

    # Format as a structured user message that the agent can parse.
    # Put button_label first so it's immediately readable.
    button_label = (
        context.pop("button_label", None) if isinstance(context, dict) else None
    )
    label_prefix = f' "{button_label}"' if button_label else ""
    context_str = json.dumps(context) if context else ""
    if context_str:
        message = f"[canvas: {action}]{label_prefix} {context_str}"
    else:
        message = f"[canvas: {action}]{label_prefix}"

    logger.info(
        f"A2UI action received — chat_id={chat_id}, surface={surface_id}, action={action}"
    )

    from suzent.core.chat_processor import ChatProcessor
    from suzent.agent_manager import build_agent_config

    processor = ChatProcessor()
    config_override = build_agent_config(config, require_social_tool=False)

    from suzent.config import CONFIG

    user_id = CONFIG.user_id

    async def streamer():
        async for chunk in processor.process_turn(
            chat_id=chat_id,
            user_id=user_id,
            message_content=message,
            config_override=config_override,
        ):
            yield chunk
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        streamer(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def a2ui_answer(request: Request) -> JSONResponse:
    """
    POST /canvas/{chat_id}/answer

    Resolves a pending ask_question deferred tool call.
    The agent is blocked waiting for this; sending the answer unblocks it
    and lets the current agent run continue (no new SSE stream needed).

    Body:
        surface_id  str   – must match the surface_id used in ask_question
        answer      dict  – the user's response data
    """
    chat_id = request.path_params.get("chat_id")
    if not chat_id:
        return JSONResponse({"error": "chat_id required"}, status_code=400)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    surface_id = data.get("surface_id", "")
    answer = data.get("answer", {})

    resolved = pending_questions.resolve(chat_id, surface_id, answer)
    if resolved:
        logger.info(
            f"Resolved pending question — chat_id={chat_id}, surface={surface_id}"
        )
        return JSONResponse({"status": "resolved"})

    return JSONResponse(
        {"error": "No pending question for this surface"}, status_code=404
    )
