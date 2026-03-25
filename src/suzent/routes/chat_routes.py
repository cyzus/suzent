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
from pathlib import Path

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.streaming import stop_stream
from suzent.core.stream_registry import get_background_queue, is_background_streaming

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

            resume_approvals_str = form.get("resume_approvals", "[]")
            try:
                resume_approvals = json.loads(resume_approvals_str)
            except json.JSONDecodeError:
                resume_approvals = []

            files_list = form.getlist("files")
            is_heartbeat = False
        else:
            data = await request.json()
            message = data.get("message", "").strip()
            # reset = data.get("reset", False)
            config = data.get("config", {})
            chat_id = data.get("chat_id")
            stream = data.get("stream", True)
            files_list = data.get("files", [])
            resume_approvals = data.get("resume_approvals", [])
            is_heartbeat = data.get("is_heartbeat", False)

        if not message and not files_list and not resume_approvals and not is_heartbeat:
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
        from suzent.agent_manager import build_agent_config

        processor = ChatProcessor()
        config_override = build_agent_config(config, require_social_tool=False)

        # When the frontend initiates a heartbeat SSE stream, claim the pending slot and
        # update heartbeat_last_run_at so the backend deferred fallback doesn't double-run.
        if is_heartbeat and chat_id:
            try:
                from suzent.core.heartbeat import get_active_heartbeat
                from suzent.database import ChatModel
                from datetime import datetime, timezone
                from sqlmodel import Session
                from sqlalchemy.orm.attributes import flag_modified

                runner = get_active_heartbeat()
                if runner:
                    runner._pending_heartbeats.pop(chat_id, None)

                    # Apply heartbeat tool-approval policy from global config.
                    from suzent.routes.heartbeat_routes import _load_heartbeat_config

                    allowed = _load_heartbeat_config().get("allowed_tools") or []
                    if allowed:
                        hb_policy = {t: "always_allow" for t in allowed}
                        existing = config_override.get("tool_approval_policy") or {}
                        config_override["tool_approval_policy"] = {
                            **existing,
                            **hb_policy,
                        }
                    else:
                        config_override["auto_approve_tools"] = True

                    # Update heartbeat_last_run_at so the deferred fallback doesn't double-run.
                    db = get_database()
                    with Session(db.engine) as _s:
                        _chat = _s.get(ChatModel, chat_id)
                        if _chat and _chat.config:
                            _chat.config["heartbeat_last_run_at"] = datetime.now(
                                timezone.utc
                            ).isoformat()
                            _chat.config.pop("heartbeat_last_result", None)
                            flag_modified(_chat, "config")
                            _s.commit()

                # Build prompt from file — frontend no longer needs to know the template.
                from suzent.prompts import (
                    HEARTBEAT_BASE_INSTRUCTIONS,
                    HEARTBEAT_PROMPT_TEMPLATE,
                )
                from pathlib import Path

                hb_path = (
                    Path(CONFIG.sandbox_data_path)
                    / "sessions"
                    / chat_id
                    / "heartbeat.md"
                )
                custom = (
                    hb_path.read_text(encoding="utf-8").strip()
                    if hb_path.exists()
                    else ""
                )
                combined = (
                    (HEARTBEAT_BASE_INSTRUCTIONS + "\n\n" + custom)
                    if custom
                    else HEARTBEAT_BASE_INSTRUCTIONS
                )
                message = HEARTBEAT_PROMPT_TEMPLATE.format(instructions=combined)
            except Exception as _hb_err:
                logger.warning(f"Heartbeat pre-processing failed: {_hb_err}")

        generator = processor.process_turn(
            chat_id=chat_id,
            user_id=CONFIG.user_id,
            message_content=message,
            files=files_list,
            config_override=config_override,
            resume_approvals=resume_approvals,
            is_heartbeat=is_heartbeat,
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
                    json_str = chunk[6:].strip()
                    if json_str == "[DONE]":
                        continue
                    event_data = json.loads(json_str)

                    msg_type = event_data.get("type")
                    if msg_type == "TEXT_MESSAGE_CONTENT":
                        full_response += event_data.get("delta", "")
                    elif msg_type == "RUN_ERROR":
                        error_msg = event_data.get("message", "Unknown error")
                        return JSONResponse({"error": error_msg}, status_code=500)
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


async def live_stream(request: Request) -> StreamingResponse:
    """Subscribe to a live background stream for a chat (cron, heartbeat, social).

    Accepts POST with JSON body: {"chat_id": "...", "wait_ms": 25000}
    Returns text/event-stream SSE (same format as /chat) if active, 204 if not.
    If `wait_ms` is provided (>0), waits up to that long for a stream to appear.
    """
    import asyncio
    from starlette.responses import Response

    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)

    chat_id = data.get("chat_id", "")
    wait_ms_raw = data.get("wait_ms", 0)
    try:
        wait_ms = max(0, int(wait_ms_raw or 0))
    except Exception:
        wait_ms = 0

    if not chat_id:
        return Response(status_code=400)

    q = get_background_queue(chat_id)
    if q is None and wait_ms > 0:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (wait_ms / 1000.0)
        while loop.time() < deadline:
            await asyncio.sleep(0.15)
            q = get_background_queue(chat_id)
            if q is not None:
                break

    if q is None:
        return Response(status_code=204)

    async def generate():
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=60.0)
            except asyncio.TimeoutError:
                # Heartbeat to keep connection alive
                yield ": keep-alive\n\n"
                continue
            if chunk is None:
                return
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

        # Convert Pydantic models to dicts, annotating live background streams
        chats_data = [
            {
                **c.model_dump(mode="json", by_alias=True),
                "isRunning": is_background_streaming(c.id),
            }
            for c in chats
        ]

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

        hb_path = Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
        if hb_path.exists():
            try:
                if "config" not in response_chat:
                    response_chat["config"] = {}
                response_chat["config"]["heartbeat_instructions"] = hb_path.read_text(
                    encoding="utf-8"
                )
            except Exception:
                pass

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
        instructions = (
            config.pop("heartbeat_instructions", None)
            if isinstance(config, dict)
            else None
        )
        messages = data.get("messages", [])

        db = get_database()
        chat_id = db.create_chat(title, config, messages)

        if instructions is not None:
            hb_path = (
                Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
            )
            try:
                hb_path.parent.mkdir(parents=True, exist_ok=True)
                hb_path.write_text(instructions, encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to write initial heartbeat.md: {e}")

        chat = db.get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Failed to create chat"}, status_code=500)

        response_chat = chat.model_dump(
            mode="json", by_alias=True, exclude={"agent_state"}
        )
        if instructions is not None:
            if "config" not in response_chat:
                response_chat["config"] = {}
            response_chat["config"]["heartbeat_instructions"] = instructions

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

        instructions = None
        if isinstance(config, dict) and "heartbeat_instructions" in config:
            instructions = config.pop("heartbeat_instructions")

        success = db.update_chat(chat_id, title=title, config=config, messages=messages)
        if not success:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

        if instructions is not None:
            hb_path = (
                Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
            )
            try:
                hb_path.parent.mkdir(parents=True, exist_ok=True)
                hb_path.write_text(instructions, encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to write heartbeat.md during update: {e}")

        chat = db.get_chat(chat_id)
        if not chat:
            return JSONResponse(
                {"error": "Failed to retrieve updated chat"}, status_code=500
            )

        response_chat = chat.model_dump(
            mode="json", by_alias=True, exclude={"agent_state"}
        )

        hb_path = Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
        if hb_path.exists():
            try:
                if "config" not in response_chat:
                    response_chat["config"] = {}
                response_chat["config"]["heartbeat_instructions"] = hb_path.read_text(
                    encoding="utf-8"
                )
            except Exception:
                pass

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


async def steer_chat(request: Request) -> StreamingResponse:
    """
    Interrupt the current agent run and redirect with a new message.

    POST /chat/steer
    {
      "chat_id": "...",
      "message": "Use Python instead",
      "config": {}           // optional
    }
    Returns SSE stream (same format as /chat).
    """
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        message = data.get("message", "").strip()
        config = data.get("config", {})

        if not chat_id:
            return JSONResponse({"error": "chat_id is required"}, status_code=400)
        if not message:
            return JSONResponse({"error": "message is required"}, status_code=400)

        from suzent.core.chat_processor import ChatProcessor
        from suzent.agent_manager import build_agent_config

        processor = ChatProcessor()
        config_override = build_agent_config(config, require_social_tool=False)

        generator = processor.process_steer(
            chat_id=chat_id,
            user_id=CONFIG.user_id,
            steer_message=message,
            config_override=config_override,
        )

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

    except Exception as e:
        logger.error(f"Error handling steer request: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


async def approve_tool(request: Request) -> JSONResponse:
    """Legacy endpoint. Approvals are now passed via /chat with resume_approvals."""
    return JSONResponse({"status": "resolved", "approved": True})
