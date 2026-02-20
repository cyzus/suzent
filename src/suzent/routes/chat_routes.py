"""
Chat-related API routes.

This module handles all chat endpoints including:
- Creating, reading, updating, and deleting chats
- Streaming chat responses
- Stopping active streams
"""

import json
import traceback

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.streaming import stop_stream

logger = get_logger(__name__)


async def chat(request: Request) -> StreamingResponse:
    """
    Handle chat requests, stream agent responses, and manage the SSE stream.

    Accepts POST with JSON body or multipart form-data containing:
    - message: The user's message
    - reset: Optional boolean to reset agent memory
    - config: Optional agent configuration
    - chat_id: Optional chat identifier
    - stream: Optional boolean (default True, JSON only)
    - files: Optional image files (multipart only)
    """
    try:
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            form = await request.form()
            message = form.get("message", "").strip()
            # reset = form.get("reset", "false").lower() == "true"
            config_str = form.get("config", "{}")
            chat_id = form.get("chat_id")
            stream = True  # Multipart always streams

            try:
                config = json.loads(config_str)
            except json.JSONDecodeError:
                config = {}

            files_list = form.getlist("files")
        else:
            data = await request.json()
            message = data.get("message", "").strip()
            # reset = data.get("reset", False)
            config = data.get("config", {})
            chat_id = data.get("chat_id")
            stream = data.get("stream", True)
            files_list = []

        if not message and not files_list:
            return StreamingResponse(
                iter(
                    ['data: {"type": "error", "data": "Empty message received."}\n\n']
                ),
                media_type="text/event-stream",
                status_code=400,
            )

        logger.info(
            f"Chat request received - chat_id: {chat_id}, "
            f"message_len: {len(message)}, files: {len(files_list)}"
        )

        from suzent.core.chat_processor import ChatProcessor

        processor = ChatProcessor()
        config_override = config.copy() if config else {}

        # Merge user preferences from DB if not provided in request
        try:
            db = get_database()
            user_prefs = db.get_user_preferences()
            if user_prefs:
                if not config_override.get("model") and user_prefs.model:
                    config_override["model"] = user_prefs.model
                if not config_override.get("agent") and user_prefs.agent:
                    config_override["agent"] = user_prefs.agent
                if "tools" not in config_override and user_prefs.tools:
                    config_override["tools"] = user_prefs.tools
        except Exception as e:
            logger.warning(f"Failed to load user preferences in chat route: {e}")

        generator = processor.process_turn(
            chat_id=chat_id,
            user_id=CONFIG.user_id,
            message_content=message,
            files=files_list,
            config_override=config_override,
        )

        if stream:
            return StreamingResponse(
                generator,
                media_type="text/event-stream",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Non-streaming: consume generator and return JSON
        full_response = ""
        async for chunk in generator:
            try:
                if chunk.startswith("data: "):
                    event_data = json.loads(chunk[6:].strip())
                    if event_data.get("type") == "final_answer":
                        full_response = event_data.get("data", "")
                    elif event_data.get("type") == "error":
                        return JSONResponse(
                            {"error": event_data.get("data")}, status_code=500
                        )
            except Exception:
                pass

        return JSONResponse({"response": full_response})

    except Exception as e:
        logger.error(f"Error handling chat request: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


async def stop_chat(request: Request) -> JSONResponse:
    """Stop an active streaming session for the given chat."""
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    chat_id = data.get("chat_id")
    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)

    reason = data.get("reason") or "Stream stopped by user"
    success = stop_stream(chat_id, reason)

    if not success:
        return JSONResponse({"status": "no_active_stream"}, status_code=404)

    return JSONResponse({"status": "stopping", "reason": reason})


async def get_chats(request: Request) -> JSONResponse:
    """Return list of chat summaries with pagination and optional search."""
    try:
        db = get_database()

        # Parse query parameters
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
        search = request.query_params.get("search", "").strip() or None

        chats = db.list_chats(limit=limit, offset=offset, search=search)
        total = db.get_chat_count(search=search)

        # Convert Pydantic models to dicts
        chats_data = [c.model_dump(mode="json", by_alias=True) for c in chats]

        return JSONResponse(
            {
                "chats": chats_data,
                "total": total,
                "limit": limit,
                "offset": offset,
                "search": search,
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_chat(request: Request) -> JSONResponse:
    """Return a specific chat by ID (excluding binary agent_state)."""
    try:
        chat_id = request.path_params["chat_id"]
        db = get_database()

        chat = db.get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

        response_chat = chat.model_dump(
            mode="json", by_alias=True, exclude={"agent_state"}
        )

        return JSONResponse(response_chat)
    except Exception as e:
        logger.error(f"Error in get_chat: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def create_chat(request: Request) -> JSONResponse:
    """Create a new chat."""
    try:
        data = await request.json()
        title = data.get("title", "New Chat")
        config = data.get("config", {})
        messages = data.get("messages", [])

        db = get_database()
        chat_id = db.create_chat(title, config, messages)

        chat = db.get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Failed to create chat"}, status_code=500)

        response_chat = chat.model_dump(
            mode="json", by_alias=True, exclude={"agent_state"}
        )
        return JSONResponse(response_chat, status_code=201)
    except Exception as e:
        logger.error(f"Error in create_chat: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_chat(request: Request) -> JSONResponse:
    """Update an existing chat."""
    try:
        chat_id = request.path_params["chat_id"]
        data = await request.json()

        db = get_database()

        title = data.get("title")
        config = data.get("config")
        messages = data.get("messages")

        success = db.update_chat(chat_id, title=title, config=config, messages=messages)
        if not success:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

        chat = db.get_chat(chat_id)
        if not chat:
            return JSONResponse(
                {"error": "Failed to retrieve updated chat"}, status_code=500
            )

        response_chat = chat.model_dump(
            mode="json", by_alias=True, exclude={"agent_state"}
        )
        return JSONResponse(response_chat)
    except Exception as e:
        logger.error(f"Error in update_chat: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def delete_chat(request: Request) -> JSONResponse:
    """Delete a chat."""
    try:
        chat_id = request.path_params["chat_id"]
        db = get_database()

        success = db.delete_chat(chat_id)
        if not success:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

        return JSONResponse({"message": "Chat deleted successfully"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
