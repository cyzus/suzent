"""Bridge ACP session updates into Suzent's AG-UI SSE and chat persistence."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator

from suzent.database import get_database

from .manager import get_acp_manager
from .permissions import PERMISSION_QUEUE_KEY


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _text_from_update(params: dict[str, Any]) -> str:
    update = params.get("update") if isinstance(params.get("update"), dict) else params
    kind = str(update.get("sessionUpdate") or update.get("type") or "")
    if kind not in {"agent_message_chunk", "agentMessageChunk", "message_chunk"}:
        return ""
    content = update.get("content")
    if isinstance(content, dict):
        return (
            str(content.get("text") or "")
            if content.get("type") in (None, "text")
            else ""
        )
    return str(update.get("text") or content or "")


async def stream_acp_turn(
    chat_id: str,
    message: str,
    config_override: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    db = get_database()
    chat = db.get_chat(chat_id)
    if chat is None:
        yield _sse({"type": "RUN_ERROR", "message": "Chat not found"})
        return
    config = {**dict(chat.config or {}), **dict(config_override or {})}
    config["runtime"] = "acp"
    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    message_open = False
    yield _sse({"type": "RUN_STARTED", "runId": run_id, "threadId": chat_id})

    try:
        requested_session = str(config.get("acp_session_id") or "").strip()
        managed = await get_acp_manager().ensure(chat_id, config)
        if requested_session and not managed.resumed:
            # The agent could not load the prior session, so history is gone.
            # Say so rather than letting it look like the agent lost its memory.
            yield _sse(
                {
                    "type": "CUSTOM",
                    "name": "acp.session_reset",
                    "value": {
                        "agentId": managed.agent_id,
                        "requestedSessionId": requested_session,
                        "sessionId": managed.session_id,
                        "reason": "load_session_unsupported",
                    },
                }
            )
        db.merge_chat_config(
            chat_id,
            {
                "runtime": "acp",
                "acp_agent_id": managed.agent_id,
                "acp_session_id": managed.session_id,
                "acp_cwd": managed.cwd,
            },
        )
        latest = db.get_chat(chat_id)
        existing = list(latest.messages or []) if latest else []

        if message and not message.strip():
            yield _sse(
                {"type": "RUN_ERROR", "message": "Empty user input is not allowed"}
            )
            return

        if message and not (
            existing
            and existing[-1].get("role") == "user"
            and existing[-1].get("content") == message
        ):
            db.append_chat_message(chat_id, {"role": "user", "content": message})

        yield _sse(
            {"type": "TEXT_MESSAGE_START", "messageId": message_id, "role": "assistant"}
        )
        message_open = True
        prompt_task = asyncio.create_task(
            managed.client.prompt(managed.session_id, message)
        )
        parts: list[str] = []
        try:
            while True:
                if prompt_task.done() and managed.updates.empty():
                    break
                try:
                    update = await asyncio.wait_for(managed.updates.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if PERMISSION_QUEUE_KEY in update:
                    yield _sse(
                        {
                            "type": "CUSTOM",
                            "name": "acp.permission_request",
                            "value": update[PERMISSION_QUEUE_KEY],
                        }
                    )
                    continue
                delta = _text_from_update(update)
                if delta:
                    parts.append(delta)
                    yield _sse(
                        {
                            "type": "TEXT_MESSAGE_CONTENT",
                            "messageId": message_id,
                            "delta": delta,
                        }
                    )
                else:
                    yield _sse(
                        {
                            "type": "CUSTOM",
                            "name": "acp.session_update",
                            "value": update,
                        }
                    )
            result = await prompt_task
        finally:
            # Never leave the prompt in flight when this generator stops early
            # (client disconnect, cancellation, or an error above).
            if not prompt_task.done():
                prompt_task.cancel()
        if not parts:
            fallback = result.get("text") or result.get("message")
            if isinstance(fallback, str) and fallback:
                parts.append(fallback)
                yield _sse(
                    {
                        "type": "TEXT_MESSAGE_CONTENT",
                        "messageId": message_id,
                        "delta": fallback,
                    }
                )
        text = "".join(parts)
        yield _sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})
        message_open = False
        if not text.strip():
            yield _sse(
                {"type": "RUN_ERROR", "message": "ACP agent produced no output text"}
            )
            return

        db.append_chat_message(chat_id, {"role": "assistant", "content": text})
        yield _sse({"type": "AGENT_FINISHED", "runId": run_id, "threadId": chat_id})
        yield "data: [DONE]\n\n"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Close the open assistant message so the UI doesn't stay stuck streaming.
        if message_open:
            yield _sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})
        yield _sse({"type": "RUN_ERROR", "message": str(exc)})


async def run_acp_turn_text(
    chat_id: str,
    message: str,
    config_override: dict[str, Any] | None = None,
    stream_queue: Any | None = None,
) -> str:
    text = ""
    async for chunk in stream_acp_turn(chat_id, message, config_override):
        if stream_queue is not None:
            await stream_queue.put(chunk)
        if chunk.startswith("data: "):
            try:
                event = json.loads(chunk[6:].strip())
            except Exception:
                continue
            if event.get("type") == "TEXT_MESSAGE_CONTENT":
                text += str(event.get("delta") or "")
    return text
