"""Bridge ACP session updates into Suzent's AG-UI SSE and chat persistence."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any, AsyncGenerator

from suzent.core.auto_title import generate_auto_title, should_generate_auto_title
from suzent.core.stream_registry import claim_pending_stop
from suzent.logger import get_logger
from suzent.database import get_database

from .manager import get_acp_manager
from .permissions import PERMISSION_QUEUE_KEY

logger = get_logger(__name__)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _attach_persistence(replay: Any | None) -> asyncio.Future[bool] | None:
    """Attach a pending persistence future to the replay this turn produces into.

    Mirrors what ChatProcessor does with its post-process task: the replay only
    emits STREAM_END{persisted:true} once this resolves True.

    The replay is passed in rather than looked up by chat_id, because a chat can
    have more than one at a time - a finished turn's, kept for a few minutes so
    a late /chat/live subscriber can drain it, or another producer's live one -
    and claiming a replay this turn is not writing to would report this turn's
    outcome as that one's. A turn with no replay attaches nothing, which is what
    `persisted` already assumes for producers that never claimed the contract.
    """
    if replay is None:
        return None
    future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    replay.persistence = future
    return future


def _resolve_persistence(future: asyncio.Future[bool] | None, value: bool) -> None:
    if future is not None and not future.done():
        future.set_result(value)


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
    go_live: Any | None = None,
) -> AsyncGenerator[str, None]:
    """Run one prompt turn, recording text, stopReason, and any agent error.

    *go_live* is called once the prompt has actually been written to the agent,
    and returns a stop reason if one was accepted while it was still on its way.
    Scheduling the request is not sending it: between `create_task` and the
    first byte the session is still idle, so a `session/cancel` sent in that
    window is answered by a session with nothing to cancel and the prompt runs
    on afterwards. Waiting for the write closes that window, and honouring
    whatever *go_live* hands back closes the one before it.
    """
    dispatched = asyncio.Event()
    prompt_task = asyncio.create_task(
        managed.client.prompt(managed.session_id, message, on_sent=dispatched.set)
    )
    try:
        # Either the request is on the wire or the attempt is already over --
        # a dead process raises before sending, and waiting for a signal that
        # is never coming would hang the turn. The loser of that race is this
        # waiter, which is never woken: dropped rather than cancelled, it and
        # its event would be held for the life of the process, one pair per
        # failed connection.
        waiter = asyncio.ensure_future(dispatched.wait())
        try:
            await asyncio.wait(
                [waiter, prompt_task], return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiter
        deferred_stop = go_live() if go_live is not None else None
        if deferred_stop:
            # Accepted while the prompt was in flight, so it was never delivered
            # to the session. Now that the agent has the prompt, it can hear it.
            await get_acp_manager().cancel(managed.chat_id)
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
    *,
    replay: Any | None = None,
) -> AsyncGenerator[str, None]:
    """Cancel the running ACP prompt, then send a new turn.

    ACP has no dedicated steer RPC — a steer is cancel + re-prompt. The new
    turn owns the replay the steer route registered for it, so it carries the
    persistence contract like any other turn.
    """
    try:
        await get_acp_manager().cancel(chat_id)
    except Exception:
        pass  # Nothing running is fine; we'll still send the new turn.
    async for event in stream_acp_turn(
        chat_id, message, config_override, replay=replay
    ):
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
    replay: Any | None = None,
) -> AsyncGenerator[str, None]:
    """Run one ACP turn, claiming the replay's persistence contract for it.

    The contract is claimed here rather than inside the turn so that it covers
    the turn's whole lifetime. A replay with no persistence future reports
    `persisted` as True the moment it closes, and everything below — the chat
    lookup, sanitizing the prompt, the agent itself — can fail or return early;
    any of those exits would otherwise end the stream with
    STREAM_END{persisted:true} for a turn that was never stored, which the
    client trusts enough to replace what it is showing.
    """
    persistence = _attach_persistence(replay)

    # A stop this run was already given, before it existed to take one. The
    # steer route registers this run's replay and then cancels the turn it
    # replaces, so a stop landing in between is accepted against this run's
    # name and left here for it. Honour it the way a stop mid-turn is honoured:
    # nothing was produced, so the persistence contract is met, and the tagged
    # error tells the client this is the stop it asked for.
    pending_stop = _claim_pending_stop(replay)
    if pending_stop:
        # The turn ran nothing, but the user did send something. The direct
        # /chat stream has no route that pre-wrote that row, so store it here
        # or the reload the client trusts after a stop comes back without the
        # prompt in it.
        stored = _persist_stopped_prompt(chat_id, message, runtime_authored, files)
        _resolve_persistence(persistence, stored)
        yield _sse(
            {"type": "RUN_ERROR", "message": pending_stop, "code": "stream_stopped"}
        )
        return

    try:
        async for chunk in _run_acp_turn(
            chat_id,
            message,
            config_override,
            persistence=persistence,
            replay=replay,
            files=files,
            file_mentions=file_mentions,
            runtime_authored=runtime_authored,
            system_preamble=system_preamble,
        ):
            yield chunk
    finally:
        # Anything that did not reach the assistant append — an early return, an
        # exception, a cancelled subscription — persisted nothing, and says so.
        _resolve_persistence(persistence, False)


def _derive_user_row(message: str, runtime_authored: bool) -> tuple[str, str, str]:
    """Sanitize a prompt and derive the transcript row it should leave.

    Returns the text to send the agent, the role to store it under, and the
    content to store. Shared with the stopped-before-it-started path, which
    stores the row without running anything.
    """
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
    return message, persisted_role, persisted_content


def _display_files(files: list[Any] | None) -> list[dict]:
    """The attachment metadata the transcript row carries, JSON-safe.

    Same shape /chat/send pre-writes, so a row stored here and a row stored
    there render as the same message. A multipart /chat request hands this path
    Starlette `UploadFile` objects instead of metadata dicts; dropping those
    would lose the attachment from the transcript entirely -- and, for a message
    that is nothing but files, leave the stopped turn with no row to promise.
    """
    rows: list[dict] = []
    for file in files or []:
        if isinstance(file, dict):
            rows.append(file)
            continue
        filename = getattr(file, "filename", None)
        if not filename:
            continue
        row: dict[str, Any] = {"filename": filename}
        mime_type = getattr(file, "content_type", None)
        if mime_type:
            row["mime_type"] = mime_type
        size = getattr(file, "size", None)
        if isinstance(size, int):
            row["size"] = size
        rows.append(row)
    return rows


def _attachment_identity(files: Any) -> list[tuple]:
    """What makes two attachment lists the same message rather than two.

    Presence alone is not enough: the same text sent twice with different files
    -- a stopped turn resent with another upload, or two file-only messages --
    would read as the row already being there, and the second message would be
    dropped while the turn promised it had been stored.
    """
    return [
        (
            str(row.get("filename") or ""),
            str(row.get("mime_type") or ""),
            row.get("size"),
        )
        for row in (files or [])
        if isinstance(row, dict)
    ]


def _append_user_row(
    db: Any,
    chat_id: str,
    existing: list[Any],
    role: str,
    content: str,
    files: list[Any] | None = None,
) -> bool:
    """Store the user's row unless the route already pre-wrote it.

    /chat/send pre-writes it so the UI has something to show before the first
    token arrives; the direct /chat stream does not. Returns whether the row is
    in the transcript afterwards, which is what a caller resolving the
    persistence contract has to promise.

    Attachments are part of that row: a message can be nothing but files, and a
    row stored without them is not the message the user sent.
    """
    attachments = _display_files(files)
    if not content.strip() and not attachments:
        return True
    if (
        existing
        and existing[-1].get("role") == role
        and str(existing[-1].get("content") or "").strip() == content.strip()
        and _attachment_identity(existing[-1].get("files"))
        == _attachment_identity(attachments)
    ):
        return True
    entry: dict[str, Any] = {"role": role, "content": content.strip()}
    if attachments:
        entry["files"] = attachments
    return bool(db.append_chat_message(chat_id, entry))


def _stopped_frames(message_id: str, reason: str) -> list[str]:
    """Close the open assistant message and report the stop the way a stop is.

    Tagged, so the client keeps listening for the STREAM_END that confirms the
    turn instead of tearing the connection down on an error notice.
    """
    return [
        _sse({"type": "TEXT_MESSAGE_END", "messageId": message_id}),
        _sse({"type": "RUN_ERROR", "message": reason, "code": "stream_stopped"}),
    ]


def _claim_pending_stop(replay: Any | None) -> str | None:
    """Take the stop that was left for this run before it could take one.

    The same claim the native path makes when it installs its control, so both
    runtimes honour a deferred stop by the one rule: cleared here, owed to the
    client by whoever cleared it.
    """
    return claim_pending_stop(replay)


def _persist_stopped_prompt(
    chat_id: str,
    message: str,
    runtime_authored: bool,
    files: list[Any] | None = None,
) -> bool:
    """Store the prompt of a turn stopped before it ever ran.

    The turn produced nothing, but the user did send something, and the client
    trusts the reload that follows a stop: without the row, that reload shows a
    history with the prompt missing. Returns whether the transcript really holds
    it, so the stop reports `persisted: false` -- and the client keeps showing
    what it has -- rather than sending the user to a reload that lost it.
    """
    try:
        db = get_database()
        chat = db.get_chat(chat_id)
        if chat is None:
            return False
        _, role, content = _derive_user_row(message, runtime_authored)
        return _append_user_row(
            db, chat_id, list(chat.messages or []), role, content, files
        )
    except Exception as exc:  # pragma: no cover - a stop must not fail on this
        # The type only. A database error carries its statement's bound
        # parameters, which here are the user's prompt and their attachments'
        # names -- exactly what must not reach a log.
        logger.debug(
            f"Could not store the prompt of a stopped ACP turn: {type(exc).__name__}"
        )
        return False


async def _run_acp_turn(
    chat_id: str,
    message: str,
    config_override: dict[str, Any] | None = None,
    *,
    persistence: asyncio.Future[bool] | None,
    files: list[Any] | None = None,
    file_mentions: list[Any] | None = None,
    runtime_authored: bool = False,
    system_preamble: str | None = None,
    replay: Any | None = None,
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
    message, persisted_role, persisted_content = _derive_user_row(
        message, runtime_authored
    )
    file_context = _build_acp_file_context(file_mentions, files)
    if file_context:
        from suzent.core.system_reminder import (
            sanitize_incoming_prompt,
            sanitize_untrusted_text,
        )

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

        stored_prompt = _append_user_row(
            db, chat_id, existing, persisted_role, persisted_content, files
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

        def _go_live() -> str | None:
            """The run's prompt is now the one the chat's session is running.

            Until this point a stop has nothing to cancel, so the route leaves
            it on the replay instead of reporting one the agent never hears;
            from here on /chat/stop answers for this run by cancelling the
            session. The handover takes any stop left in that window, so one
            that arrived a moment too early is carried out rather than
            stranded.
            """
            if replay is None:
                return None
            replay.producer_started = True
            return _claim_pending_stop(replay)

        # Connecting the session is the longest part of a turn, and a stop that
        # arrives during it has no prompt to cancel. This is the last moment one
        # can be honoured for free: before it, the agent has been given nothing
        # at all.
        pending_stop = _claim_pending_stop(replay)
        if pending_stop:
            message_open = False
            # The agent was never prompted, so nothing it produced is missing --
            # only the user's row has to be there, and the turn says so only if
            # it really is.
            _resolve_persistence(persistence, stored_prompt)
            for frame in _stopped_frames(message_id, pending_stop):
                yield frame
            return
        async for event in _stream_prompt(
            managed, _prompt, message_id, state, _go_live
        ):
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
            # The session that was running this turn's prompt is gone, and
            # building a fresh one takes as long as the first connect did. The
            # run is not live for that window: a stop landing in it has nothing
            # to cancel, so it belongs back on the replay rather than being
            # reported against a session that cannot carry it out.
            if replay is not None:
                replay.producer_started = False
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
            # Same rule as the first prompt: take any stop from the reconnect
            # window here, and only then say the new session is running this
            # run's prompt.
            pending_stop = _claim_pending_stop(replay)
            if pending_stop:
                message_open = False
                _resolve_persistence(persistence, stored_prompt)
                for frame in _stopped_frames(message_id, pending_stop):
                    yield frame
                return
            # _prompt, not message: the retry is the same request, so it needs
            # the same preamble. Passing `message` here dropped the precedence
            # rules for exactly the sub-agents that recovered from a stale
            # session.
            async for event in _stream_prompt(
                managed, _prompt, message_id, state, _go_live
            ):
                yield event

        text = "".join(state["parts"])
        yield _sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})
        message_open = False
        if not text.strip():
            if state.get("stop_reason") == "cancelled":
                # A stop is not a failure here either. The native path tags its
                # own cancellation frame the same way, and the client reads the
                # tag to keep listening for the stream's real ending instead of
                # tearing the connection down on an error notice.
                #
                # The contract is "everything this turn produced is in the
                # database", and a turn stopped before its first token produced
                # nothing from the agent -- so the user's row is all of it.
                # Where that row landed the contract is met, and saying
                # otherwise would turn the stop the client just accepted back
                # into "Stream persistence failed"; where it did not, the
                # reload this promise sends the client to would come back
                # without the prompt they just sent.
                _resolve_persistence(persistence, stored_prompt)
                yield _sse(
                    {
                        "type": "RUN_ERROR",
                        "message": "Stream stopped by user",
                        "code": "stream_stopped",
                    }
                )
                return
            yield _sse({"type": "RUN_ERROR", "message": _no_output_error(state)})
            return

        # The restored session has now proven it can run a turn.
        managed.restored = False
        # Stamp the agent that produced this response, matching the native
        # per-message model signature, so the transcript doesn't label an ACP
        # answer with the chat's unused native model.
        # False, not an exception, when the chat was deleted mid-turn: the row
        # does not exist, so the turn is not persisted and must not claim to be.
        stored = db.append_chat_message(
            chat_id,
            {
                "role": "assistant",
                "content": text,
                "model": f"acp/{managed.agent_id}",
            },
        )
        _resolve_persistence(persistence, stored is not False)
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
        replay=getattr(stream_queue, "replay", None),
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
