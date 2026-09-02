"""Bridge ACP session updates into Suzent's AG-UI SSE and chat persistence."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator

from suzent.core.auto_title import generate_auto_title, should_generate_auto_title
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


def _turn_error_from_update(params: dict[str, Any]) -> str:
    """Return the agent's error text when an update reports a failed turn."""
    if not isinstance(params, dict):
        return ""
    if (
        str(params.get("status") or "") != "turn_error"
        and str(params.get("phase") or "") != "error"
    ):
        return ""
    message = params.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return "the agent reported a failed turn"


async def _stream_prompt(
    managed: Any,
    message: str,
    message_id: str,
    state: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Run one prompt turn, recording text, stopReason, and any agent error."""
    prompt_task = asyncio.create_task(
        managed.client.prompt(managed.session_id, message)
    )
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
            failure = _turn_error_from_update(update)
            if failure:
                state["error"] = failure
            delta = _text_from_update(update)
            if delta:
                state["parts"].append(delta)
                yield _sse(
                    {
                        "type": "TEXT_MESSAGE_CONTENT",
                        "messageId": message_id,
                        "delta": delta,
                    }
                )
            else:
                yield _sse(
                    {"type": "CUSTOM", "name": "acp.session_update", "value": update}
                )
        result = await prompt_task
    finally:
        # Never leave the prompt in flight when this generator stops early
        # (client disconnect, cancellation, or an error above).
        if not prompt_task.done():
            prompt_task.cancel()

    state["stop_reason"] = str(result.get("stopReason") or "")
    if not state["parts"]:
        fallback = result.get("text") or result.get("message")
        if isinstance(fallback, str) and fallback:
            state["parts"].append(fallback)
            yield _sse(
                {
                    "type": "TEXT_MESSAGE_CONTENT",
                    "messageId": message_id,
                    "delta": fallback,
                }
            )


def _no_output_error(state: dict[str, Any]) -> str:
    """Explain an empty turn using whatever the agent actually told us."""
    if state.get("error"):
        return f"ACP agent error: {state['error']}"
    stop_reason = state.get("stop_reason") or ""
    if stop_reason and stop_reason != "end_turn":
        return f"ACP agent stopped without output (stopReason: {stop_reason})"
    return "ACP agent produced no output text"


def _build_acp_file_context(
    file_mentions: list[Any] | None = None,
    files: list[Any] | None = None,
) -> str:
    """Annotate the ACP prompt with user-referenced paths.

    ACP agents run locally so file paths are actionable.  Binary uploads
    (``files``) can't be forwarded over the text-only prompt channel; a
    warning event is emitted instead by the caller.
    """
    parts: list[str] = []
    for item in file_mentions or []:
        if isinstance(item, dict):
            path = item.get("path")
            kind = "directory" if item.get("type") == "directory" else "file"
        else:
            path = item
            kind = "file"
        if path:
            parts.append(f"[User referenced {kind}: {path}]")
    return "\n".join(parts)


async def stream_acp_steer(
    chat_id: str,
    message: str,
    config_override: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """Cancel the running ACP prompt, then send a new turn.

    ACP has no dedicated steer RPC — a steer is cancel + re-prompt.
    """
    try:
        await get_acp_manager().cancel(chat_id)
    except Exception:
        pass  # Nothing running is fine; we'll still send the new turn.
    async for event in stream_acp_turn(chat_id, message, config_override):
        yield event


async def stream_acp_turn(
    chat_id: str,
    message: str,
    config_override: dict[str, Any] | None = None,
    *,
    files: list[Any] | None = None,
    file_mentions: list[Any] | None = None,
    runtime_authored: bool = False,
    system_preamble: str | None = None,
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
    # Annotate the prompt with user-referenced file paths so the ACP agent
    # can act on them — it runs locally and has filesystem access.
    # Only the agent sees that annotation; the transcript keeps what the user
    # typed. Comparing the annotated text against the stored row defeated the
    # duplicate check below and persisted the message twice.
    from suzent.core.system_reminder import (
        extract_system_reminder_display_trigger,
        sanitize_incoming_prompt,
        sanitize_untrusted_text,
        strip_system_reminders,
    )

    # Sanitize before deriving the transcript *and* before running the turn, so
    # the two cannot disagree. Without this, a message wrapping its payload in a
    # nonce-shaped reminder block strips to nothing visible and persists only its
    # own chosen display trigger, while the raw text still reaches
    # _stream_prompt() below — a prompt that executes but is misrepresented in
    # the audit transcript. Runtime-authored blocks carry our token and survive,
    # so genuine cron and heartbeat triggers still render as trigger rows.
    #
    # The ingress variant, not the history one: this message is being sent now,
    # so forged delimiters are escaped in place rather than deleted. Dropping
    # would lose text the user meant to send, and a message that was nothing but
    # a block would empty out and slip past the truthiness check below as a blank
    # turn.
    #
    # Provenance comes from *runtime_authored*, never from the token in the text.
    # RUNTIME_NONCE is embedded in every reminder the model reads, so it is a
    # bearer token the untrusted side can observe and replay: honouring it on
    # externally supplied input would let a message that echoes it back be
    # treated as runtime context and vanish from the transcript. Only the
    # internal caller that built the reminder may claim that status, and it says
    # so on the call rather than in the string.
    if message:
        message = (
            sanitize_incoming_prompt(message)
            if runtime_authored
            else sanitize_untrusted_text(message)
        )
    user_message = message

    display_trigger = extract_system_reminder_display_trigger(user_message)
    visible_user_message = strip_system_reminders(user_message)
    persisted_role = (
        "system_triggered" if display_trigger and not visible_user_message else "user"
    )
    persisted_content = (
        display_trigger
        if persisted_role == "system_triggered"
        else visible_user_message
    )
    file_context = _build_acp_file_context(file_mentions, files)
    if file_context:
        message = f"{file_context}\n\n{message}" if message else file_context
        # File annotations interpolate caller-supplied paths, so the assembled
        # prompt is untrusted again even though `message` was already clean.
        # Sanitizing the finished string rather than only its parts is the point:
        # anything later prepended or appended here is covered without having to
        # remember it. Idempotent, so the already-clean portion is unaffected.
        message = (
            sanitize_incoming_prompt(message)
            if runtime_authored
            else sanitize_untrusted_text(message)
        )

    # Binary uploads can't be forwarded over the text-only ACP prompt channel.
    if files:
        yield _sse(
            {
                "type": "CUSTOM",
                "name": "acp.files_unsupported",
                "value": {
                    "count": len(files),
                    "message": (
                        "File uploads are not forwarded to ACP agents. "
                        "Referenced file paths are included in the prompt."
                    ),
                },
            }
        )

    yield _sse({"type": "RUN_STARTED", "runId": run_id, "threadId": chat_id})

    title_task: asyncio.Task[Any] | None = None
    try:
        requested_session = str(config.get("acp_session_id") or "").strip()
        managed = await get_acp_manager().ensure(chat_id, config)
        load_error = str(getattr(managed, "load_error", "") or "")
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
                        "reason": (
                            "load_session_failed"
                            if load_error
                            else "load_session_unsupported"
                        ),
                        "detail": load_error,
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

        # /chat/send pre-writes the user's row so the UI has something to show
        # before the first token arrives; only append when that didn't happen.
        if persisted_content.strip() and not (
            existing
            and existing[-1].get("role") == persisted_role
            and str(existing[-1].get("content") or "").strip()
            == persisted_content.strip()
        ):
            db.append_chat_message(
                chat_id, {"role": persisted_role, "content": persisted_content.strip()}
            )

        # Auto-titling lives in suzent.streaming, which an ACP turn never goes
        # through -- so every ACP chat stayed named "New Chat". The title comes
        # from the `cheap` role, not from the ACP agent, so it costs the turn
        # nothing and runs alongside it.
        if (
            persisted_role == "user"
            and persisted_content.strip()
            and should_generate_auto_title(latest)
        ):
            title_task = asyncio.create_task(
                generate_auto_title(chat_id, persisted_content.strip())
            )

        yield _sse(
            {"type": "TEXT_MESSAGE_START", "messageId": message_id, "role": "assistant"}
        )
        message_open = True

        state: dict[str, Any] = {"parts": [], "stop_reason": "", "error": ""}
        # Model-only. The transcript rows were derived from `message` above, so
        # anything added here reaches the agent without being recorded as
        # something the user said — internal policy text in a persisted user row
        # misrepresents the conversation to anyone auditing it later.
        _prompt = f"{system_preamble}\n{message}" if system_preamble else message
        async for event in _stream_prompt(managed, _prompt, message_id, state):
            yield event

        # A session restored with session/load that fails its very first turn is
        # almost always stale: the agent accepted an id its process no longer
        # backs, which only surfaces here. Start a fresh session and try once
        # more, so a chat isn't permanently broken after the agent restarts.
        if (
            managed.restored
            and not "".join(state["parts"]).strip()
            and state["stop_reason"] == "error"
        ):
            managed = await get_acp_manager().create(
                chat_id,
                managed.agent_id,
                managed.cwd,
                str(config.get("permission_mode") or ""),
            )
            db.merge_chat_config(chat_id, {"acp_session_id": managed.session_id})
            yield _sse(
                {
                    "type": "CUSTOM",
                    "name": "acp.session_reset",
                    "value": {
                        "agentId": managed.agent_id,
                        "requestedSessionId": requested_session,
                        "sessionId": managed.session_id,
                        "reason": "stale_session",
                    },
                }
            )
            state = {"parts": [], "stop_reason": "", "error": ""}
            # _prompt, not message: the retry is the same request, so it needs
            # the same preamble. Passing `message` here dropped the precedence
            # rules for exactly the sub-agents that recovered from a stale
            # session.
            async for event in _stream_prompt(managed, _prompt, message_id, state):
                yield event

        text = "".join(state["parts"])
        yield _sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})
        message_open = False
        if not text.strip():
            yield _sse({"type": "RUN_ERROR", "message": _no_output_error(state)})
            return

        # The restored session has now proven it can run a turn.
        managed.restored = False
        # Stamp the agent that produced this response, matching the native
        # per-message model signature, so the transcript doesn't label an ACP
        # answer with the chat's unused native model.
        db.append_chat_message(
            chat_id,
            {
                "role": "assistant",
                "content": text,
                "model": f"acp/{managed.agent_id}",
            },
        )
        if title_task is not None:
            try:
                title = await title_task
            except Exception:
                title = None
            if title:
                yield _sse(
                    {
                        "type": "CUSTOM",
                        "name": "chat_title_updated",
                        "value": {"chat_id": chat_id, "title": title},
                    }
                )

        yield _sse({"type": "AGENT_FINISHED", "runId": run_id, "threadId": chat_id})
        yield "data: [DONE]\n\n"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Close the open assistant message so the UI doesn't stay stuck streaming.
        if message_open:
            yield _sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})
        yield _sse({"type": "RUN_ERROR", "message": str(exc)})
    finally:
        # A failed or abandoned turn shouldn't leave a title lookup in flight.
        if title_task is not None and not title_task.done():
            title_task.cancel()


async def run_acp_turn_text(
    chat_id: str,
    message: str,
    config_override: dict[str, Any] | None = None,
    stream_queue: Any | None = None,
    *,
    runtime_authored: bool = False,
    system_preamble: str | None = None,
) -> str:
    text = ""
    async for chunk in stream_acp_turn(
        chat_id,
        message,
        config_override,
        runtime_authored=runtime_authored,
        system_preamble=system_preamble,
    ):
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
