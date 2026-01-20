"""
Chat-related API routes.

This module handles all chat endpoints including:
- Creating, reading, updating, and deleting chats
- Streaming chat responses
- Stopping active streams
"""

import base64
import io
import json
import traceback
import uuid
from typing import Any, Dict, List

from PIL import Image
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.agent_manager import (
    deserialize_agent,
    get_memory_manager,
    get_or_create_agent,
    inject_chat_context,
    serialize_agent,
)
from suzent.config import CONFIG
from suzent.database import get_database
from suzent.image_utils import compress_image_with_bytes
from suzent.logger import get_logger
from suzent.memory import AgentStepsSummary, ConversationTurn, Message
from suzent.streaming import stop_stream, stream_agent_responses

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
        images_data: List[Dict[str, Any]] = []
        pil_images = []

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

            # Process uploaded images (compress and prepare for agent)
            files = form.getlist("files")
            for file in files:
                try:
                    # Load image from upload
                    content = await file.read()
                    image = Image.open(io.BytesIO(content))

                    # Compress image - returns both PIL Image and compressed bytes
                    # Use 0.25 MB limit because smolagents re-encodes PIL Images dramatically
                    # Observed: 0.4 MB JPEG → 5.7 MB after re-encoding (14x expansion!)
                    # Target 0.25 MB JPEG → ~3.5 MB after smolagents re-encoding → safe under 5 MB
                    compressed_image, compressed_bytes = compress_image_with_bytes(
                        image, max_size_mb=0.25
                    )

                    # Verify final size
                    size_mb = len(compressed_bytes) / (1024 * 1024)
                    logger.info(
                        f"Compressed {file.filename}: {compressed_image.width}x{compressed_image.height}, {size_mb:.2f} MB"
                    )

                    # Add to agent input (PIL Image)
                    pil_images.append(compressed_image)

                    # Store metadata with pre-compressed bytes (no re-encoding!)
                    images_data.append(
                        {
                            "id": str(uuid.uuid4()),
                            "data": base64.b64encode(compressed_bytes).decode("utf-8"),
                            "mime_type": "image/jpeg",
                            "filename": file.filename or "image.jpg",
                            "width": compressed_image.width,
                            "height": compressed_image.height,
                        }
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to process image {getattr(file, 'filename', 'unknown')}: {e}"
                    )
                    continue
        else:
            # Handle JSON (backward compatibility)
            data = await request.json()
            message = data.get("message", "").strip()
            reset = data.get("reset", False)
            config = data.get("config", {})
            chat_id = data.get("chat_id")

        if not message:
            return StreamingResponse(
                iter(
                    ['data: {"type": "error", "data": "Empty message received."}\n\n']
                ),
                media_type="text/event-stream",
                status_code=400,
            )

        async def response_generator():
            try:
                # Send image metadata to frontend if images were uploaded
                if images_data:
                    yield f"data: {json.dumps({'type': 'images_processed', 'data': images_data})}\n\n"

                # Inject user_id and chat_id into config for memory system
                config["_user_id"] = CONFIG.user_id
                config["_chat_id"] = chat_id

                # Extract facts from user message FIRST (before retrieval)
                # This ensures facts from current message are available for search
                memory_enabled = config.get("memory_enabled", False)

                # NOTE: Extraction moved to AFTER streaming to capture full agent context (Phase 2)

                # Retrieve relevant memories and inject into context (after extraction)
                memory_context = ""
                if chat_id and message and memory_enabled:
                    try:
                        memory_mgr = get_memory_manager()
                        if memory_mgr:
                            # Retrieve relevant memories for the user's query
                            memory_context = (
                                await memory_mgr.retrieve_relevant_memories(
                                    query=message,
                                    chat_id=chat_id,
                                    user_id=CONFIG.user_id,
                                    limit=AUTO_RETRIEVAL_MEMORY_LIMIT,
                                )
                            )
                            if memory_context:
                                logger.info(
                                    f"Injecting relevant memories into context for chat {chat_id}"
                                )
                    except Exception as e:
                        logger.debug(f"Memory retrieval skipped: {e}")

                # Get or create agent with specified configuration
                agent_instance = await get_or_create_agent(config, reset=reset)
                logger.debug(
                    f"Agent from get_or_create_agent has tools: {[t.__class__.__name__ for t in agent_instance._tool_instances]}"
                )

                # If we have a chat_id and not resetting, try to restore agent state
                if chat_id and not reset:
                    try:
                        db = get_database()
                        chat = db.get_chat(chat_id)

                        if chat and chat.agent_state:
                            logger.debug(
                                f"Attempting to restore agent state for chat {chat_id}"
                            )
                            restored_agent = deserialize_agent(chat.agent_state, config)
                            if restored_agent:
                                logger.debug(
                                    f"Restored agent has tools: {[t.__class__.__name__ for t in restored_agent._tool_instances]}"
                                )
                                agent_instance = restored_agent
                                logger.debug(
                                    "Replaced agent_instance with restored_agent"
                                )
                            else:
                                # Agent state was corrupted (e.g., incompatible library version)
                                # Clear it from database so fresh state can be saved
                                logger.info(
                                    f"Clearing corrupted agent state for chat {chat_id}"
                                )
                                db.update_chat(chat_id, agent_state=b"")
                    except Exception as e:
                        logger.warning(f"Error loading agent state: {e}")
                        # Continue without state restoration rather than failing

                # Inject chat_id, user_id, and config into tools if available
                if chat_id:
                    user_id = config.get("_user_id", CONFIG.user_id)
                    inject_chat_context(agent_instance, chat_id, user_id, config)

                # Inject memory context into agent instructions (ephemeral)
                # We do this instead of prepending to message to keep the user's query clean
                # and treat memory as system-level context.
                original_instructions = getattr(agent_instance, "instructions", "")
                if memory_context:
                    logger.debug(f"Injecting memory context:\n{memory_context}")
                    agent_instance.instructions = (
                        f"{original_instructions}\n\n{memory_context}"
                    )
                    logger.debug(
                        f"Final Agent Instructions:\n{agent_instance.instructions}"
                    )

                try:
                    # Stream agent responses (pass PIL images to agent)
                    async for chunk in stream_agent_responses(
                        agent_instance,
                        message,
                        reset=reset,
                        chat_id=chat_id,
                        images=pil_images if pil_images else None,
                    ):
                        yield chunk

                    # Extract memories from the full conversation turn (Phase 1 & 2)
                    if chat_id and memory_enabled:
                        try:
                            memory_mgr = get_memory_manager()

                            if memory_mgr:
                                # Phase 1: Access agent memory for context
                                succinct_steps = (
                                    agent_instance.memory.get_succinct_steps()
                                )

                                # Debug: Show what steps we got
                                logger.debug(
                                    f"Retrieved {len(succinct_steps)} succinct steps from agent memory"
                                )

                                steps = AgentStepsSummary.from_succinct_steps(
                                    succinct_steps
                                )
                                logger.debug(
                                    f"Created AgentStepsSummary: {len(steps.actions)} actions, {len(steps.planning)} planning steps, has_answer={bool(steps.final_answer)}"
                                )

                                # Phase 2: Build ConversationTurn for extraction
                                conversation_turn = ConversationTurn(
                                    user_message=Message(role="user", content=message),
                                    assistant_message=Message(
                                        role="assistant", content=steps.final_answer
                                    ),
                                    agent_actions=steps.actions,
                                    agent_reasoning=steps.planning,
                                )

                                logger.debug(
                                    f"Extracting memories from turn:\nUser: {message}\nAssistant: {steps.final_answer}"
                                )

                                await memory_mgr.process_conversation_turn_for_memories(
                                    conversation_turn=conversation_turn,
                                    chat_id=chat_id,
                                    user_id=CONFIG.user_id,
                                )

                        except Exception as e:
                            logger.error(
                                f"Error extracting memories from conversation turn: {e}"
                            )
                            logger.error(traceback.format_exc())

                finally:
                    # Restore original instructions to avoid persisting ephemeral memory context
                    if memory_context:
                        agent_instance.instructions = original_instructions

                # Save agent state after streaming completes
                if chat_id:
                    try:
                        agent_state = serialize_agent(agent_instance)
                        if agent_state:
                            db = get_database()
                            db.update_chat(chat_id, agent_state=agent_state)
                    except Exception as e:
                        logger.error(
                            f"Error saving agent state for chat {chat_id}: {e}"
                        )

            except Exception as e:
                traceback.print_exc()
                yield f'data: {{"type": "error", "data": "Error creating agent: {e!s}"}}\n\n'

        return StreamingResponse(
            response_generator(),
            media_type="text/event-stream",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except json.JSONDecodeError:
        return StreamingResponse(
            iter(['data: {"type": "error", "data": "Invalid JSON."}\n\n']),
            media_type="text/event-stream",
            status_code=400,
        )
    except Exception as e:
        return StreamingResponse(
            iter(
                [
                    f'data: {{"type": "error", "data": "An unexpected error occurred: {e!s}"}}\n\n'
                ]
            ),
            media_type="text/event-stream",
            status_code=500,
        )


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
