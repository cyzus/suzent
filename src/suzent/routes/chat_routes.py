"""
Chat-related API routes.

This module handles all chat endpoints including:
- Creating, reading, updating, and deleting chats
- Streaming chat responses
- Stopping active streams
"""

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.streaming import stop_stream

import json
import traceback
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

logger = get_logger(__name__)

# Memory retrieval configuration
AUTO_RETRIEVAL_MEMORY_LIMIT = 5


async def chat(request: Request) -> StreamingResponse:
    """
    Handles chat requests, streams agent responses, and manages the SSE stream.

    Accepts POST requests with either:
    1. JSON body containing:
       - message: The user's message
       - reset: Optional boolean to reset agent memory
       - config: Optional agent configuration
       - chat_id: Optional chat identifier for context

    2. Multipart form-data containing:
       - message: The user's message (text field)
       - reset: Optional boolean as string (form field)
       - config: Optional agent configuration as JSON string (form field)
       - chat_id: Optional chat identifier (form field)
       - files: Optional image files (file uploads)

    Returns:
        StreamingResponse with server-sent events.
    """
    try:
        # Check content type to determine how to parse the request
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            # Handle multipart form data
            form = await request.form()
            message = form.get("message", "").strip()
            reset = form.get("reset", "false").lower() == "true"
            config_str = form.get("config", "{}")
            chat_id = form.get("chat_id")

            # Parse config from JSON string
            try:
                config = json.loads(config_str)
            except json.JSONDecodeError:
                config = {}

            # Get list of UploadFile objects (no processing yet)
            files_list = form.getlist("files")
        else:
            # Handle JSON (backward compatibility)
            data = await request.json()
            message = data.get("message", "").strip()
            reset = data.get("reset", False)
            config = data.get("config", {})
            chat_id = data.get("chat_id")
            files_list = []  # No file support in pure JSON mode yet (unless base64 encoded, but ChatProcessor handles UploadFile/dict)

        if not message and not files_list:
            return StreamingResponse(
                iter(
                    ['data: {"type": "error", "data": "Empty message received."}\n\n']
                ),
                media_type="text/event-stream",
                status_code=400,
            )

        # Delegate to ChatProcessor
        try:
            logger.info(
                f"Chat request received - chat_id: {chat_id}, message_len: {len(message)}, files: {len(files_list)}"
            )
            from suzent.core.chat_processor import ChatProcessor

            processor = ChatProcessor()

            # Prepare config overrides from request body
            # We pass the entire config object so that tools, mcp settings, etc. are respected.
            config_override = config.copy() if config else {}

            if reset:
                # TODO: Implement explicit reset support via ChatProcessor
                # Currently handled implicitly when config changes
                pass

            # Return StreamingResponse using the processor's generator
            return StreamingResponse(
                processor.process_turn(
                    chat_id=chat_id,
                    user_id=CONFIG.user_id,
                    message_content=message,
                    files=files_list,
                    config_override=config_override,
                ),
                media_type="text/event-stream",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        except Exception as e:
            logger.error(f"Chat processing failed: {e}")
            return StreamingResponse(
                iter(
                    [
                        f'data: {{"type": "error", "data": "Processing failed: {e!s}"}}\n\n'
                    ]
                ),
                media_type="text/event-stream",
                status_code=500,
            )

    except Exception as e:
        logger.error(f"Error handling chat request: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


async def stop_chat(request: Request) -> JSONResponse:
    """
    Stop an active streaming session for the given chat.

    Accepts POST requests with JSON body containing:
    - chat_id: The chat identifier for the stream to stop
    - reason: Optional reason for stopping (default: "Stream stopped by user")

    Returns:
        JSONResponse with status and reason.
    """
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
    """
    Return list of chat summaries.

    Query parameters:
    - limit: Maximum number of chats to return (default: 50)
    - offset: Number of chats to skip (default: 0)
    - search: Optional search query to filter chats by title or message content

    Returns:
        JSONResponse with chats list, total count, and pagination info.
    """
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
    """
    Return a specific chat by ID.

    Path parameter:
    - chat_id: The chat identifier

    Returns:
        JSONResponse with chat details (excluding binary agent_state).
    """
    try:
        chat_id = request.path_params["chat_id"]
        db = get_database()

        chat = db.get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

        # Remove agent_state from response and use alias for camelCase timestamps
        response_chat = chat.model_dump(
            mode="json", by_alias=True, exclude={"agent_state"}
        )

        return JSONResponse(response_chat)
    except Exception as e:
        logger.error(f"Error in get_chat: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def create_chat(request: Request) -> JSONResponse:
    """
    Create a new chat.

    Accepts POST requests with JSON body containing:
    - title: Chat title (default: "New Chat")
    - config: Optional chat configuration
    - messages: Optional initial messages list

    Returns:
        JSONResponse with created chat details.
    """
    try:
        data = await request.json()
        title = data.get("title", "New Chat")
        config = data.get("config", {})
        messages = data.get("messages", [])

        db = get_database()
        chat_id = db.create_chat(title, config, messages)

        # Return the created chat (excluding binary agent_state)
        chat = db.get_chat(chat_id)
        if chat:
            response_chat = chat.model_dump(
                mode="json", by_alias=True, exclude={"agent_state"}
            )
            return JSONResponse(response_chat, status_code=201)
        else:
            return JSONResponse({"error": "Failed to create chat"}, status_code=500)
    except Exception as e:
        logger.error(f"Error in create_chat: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_chat(request: Request) -> JSONResponse:
    """
    Update an existing chat.

    Path parameter:
    - chat_id: The chat identifier

    Accepts PUT requests with JSON body containing optional fields:
    - title: Updated chat title
    - config: Updated configuration
    - messages: Updated messages list

    Returns:
        JSONResponse with updated chat details.
    """
    try:
        chat_id = request.path_params["chat_id"]
        data = await request.json()

        db = get_database()

        # Extract update fields
        title = data.get("title")
        config = data.get("config")
        messages = data.get("messages")

        success = db.update_chat(chat_id, title=title, config=config, messages=messages)
        if not success:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

        # Return updated chat (excluding binary agent_state)
        chat = db.get_chat(chat_id)
        if chat:
            response_chat = chat.model_dump(
                mode="json", by_alias=True, exclude={"agent_state"}
            )
            return JSONResponse(response_chat)
        else:
            return JSONResponse(
                {"error": "Failed to retrieve updated chat"}, status_code=500
            )
    except Exception as e:
        logger.error(f"Error in update_chat: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def delete_chat(request: Request) -> JSONResponse:
    """
    Delete a chat.

    Path parameter:
    - chat_id: The chat identifier

    Returns:
        JSONResponse with success message.
    """
    try:
        chat_id = request.path_params["chat_id"]
        db = get_database()

        success = db.delete_chat(chat_id)
        if not success:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

        return JSONResponse({"message": "Chat deleted successfully"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
