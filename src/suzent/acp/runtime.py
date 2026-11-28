"""Bridge ACP session updates into Suzent's AG-UI SSE and chat persistence."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, AsyncGenerator

from suzent.core.auto_title import generate_auto_title, should_generate_auto_title
from suzent.core.stream_registry import claim_pending_stop
from suzent.core.chat_mentions import build_chat_mention_context
from suzent.logger import get_logger
from suzent.database import get_database

from .manager import get_acp_manager
from .client import ACPError
from .permissions import PERMISSION_QUEUE_KEY

logger = get_logger(__name__)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _parse_sse(chunk: str) -> dict[str, Any]:
    """The event an SSE chunk carries, or an empty dict for anything else."""
    if not chunk.startswith("data: "):
        return {}
    try:
        event = json.loads(chunk[6:].strip())
    except Exception:
        return {}
    return event if isinstance(event, dict) else {}


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


def _thought_from_update(params: dict[str, Any]) -> str:
    update = params.get("update") if isinstance(params.get("update"), dict) else params
    kind = str(update.get("sessionUpdate") or update.get("type") or "")
    if kind not in {"agent_thought_chunk", "agentThoughtChunk", "thought_chunk"}:
        return ""
    content = update.get("content")
    if isinstance(content, dict):
        return (
            str(content.get("text") or "")
            if content.get("type") in (None, "text")
            else ""
        )
    return str(update.get("text") or content or "")


def _user_text_from_update(params: dict[str, Any]) -> str:
    update = params.get("update") if isinstance(params.get("update"), dict) else params
    kind = str(update.get("sessionUpdate") or update.get("type") or "")
    if kind not in {"user_message_chunk", "userMessageChunk"}:
        return ""
    content = update.get("content")
    if isinstance(content, dict):
        return (
            str(content.get("text") or "")
            if content.get("type") in (None, "text")
            else ""
        )
    return str(update.get("text") or content or "")


def _infer_acp_tool_name(update: dict[str, Any]) -> str:
    for key in ("name", "toolName", "tool_name"):
        val = update.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    kind = str(update.get("kind") or "").strip().lower()
    raw_input = update.get("rawInput") or update.get("input")
    if kind == "read":
        return "read_file"
    if kind in ("edit", "write"):
        if isinstance(raw_input, dict) and (
            "old_string" in raw_input or "oldText" in raw_input
        ):
            return "edit_file"
        content = update.get("content")
        if isinstance(content, list) and any(
            isinstance(c, dict) and c.get("type") == "diff" for c in content
        ):
            return "edit_file"
        return "edit_file" if kind == "edit" else "write_file"
    if kind in ("execute", "bash", "command", "terminal"):
        return "run_command"
    if kind == "search":
        if isinstance(raw_input, dict) and ("query" in raw_input or "url" in raw_input):
            return "web_search"
        return "grep_search"
    if kind == "fetch":
        return "webpage_fetch"
    if kind == "think":
        return "think"
    title = str(update.get("title") or "").strip()
    if title:
        first_word = title.split()[0].lower().rstrip(":")
        if first_word in (
            "read",
            "write",
            "edit",
            "bash",
            "glob",
            "grep",
            "websearch",
            "webfetch",
            "task",
        ):
            return first_word
        return title[:48]
    return kind or "tool"


def _normalize_acp_raw_input(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Ensure ACP rawInput dictionaries also expose Suzent's native arg keys."""
    out = dict(raw_input)
    if "content" not in out:
        for cmd_key in ("command", "cmd", "script"):
            val = out.get(cmd_key)
            if isinstance(val, str) and val.strip():
                out["content"] = val
                break
            if isinstance(val, list) and val and all(isinstance(x, str) for x in val):
                out["content"] = " ".join(val)
                break
    return out


def _extract_acp_tool_args(update: dict[str, Any]) -> tuple[str, bool]:
    """Return ``(args_json, is_authoritative)`` for an ACP tool update.

    Authoritative inputs come from ``rawInput`` / ``input`` or from ``diff``
    content blocks carrying actual ``newText`` / ``oldText`` edits. Metadata
    fallbacks (``locations``, path-only diffs, or ``title``) are used only when
    no authoritative arguments have been seen yet for a tool call.
    """
    raw_input = update.get("rawInput")
    if raw_input is None:
        raw_input = update.get("input")
    if isinstance(raw_input, dict) and raw_input:
        return json.dumps(_normalize_acp_raw_input(raw_input), ensure_ascii=False), True
    if isinstance(raw_input, str) and raw_input.strip():
        return raw_input.strip(), True
    content = update.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "diff":
                path = block.get("path")
                old_text = block.get("oldText")
                new_text = block.get("newText")
                if (
                    isinstance(path, str)
                    and path
                    and (
                        (isinstance(old_text, str) and old_text)
                        or (isinstance(new_text, str) and new_text)
                    )
                ):
                    diff_args: dict[str, Any] = {
                        "file_path": path,
                        "old_string": old_text if isinstance(old_text, str) else "",
                        "new_string": new_text if isinstance(new_text, str) else "",
                    }
                    return json.dumps(diff_args, ensure_ascii=False), True
    locations = update.get("locations")
    if isinstance(locations, list) and locations:
        first = locations[0]
        if isinstance(first, dict) and isinstance(first.get("path"), str):
            return json.dumps({"path": first["path"]}, ensure_ascii=False), False
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "diff":
                path = block.get("path")
                if isinstance(path, str) and path:
                    return json.dumps({"path": path}, ensure_ascii=False), False
    title = str(update.get("title") or "").strip()
    if title:
        return json.dumps({"description": title}, ensure_ascii=False), False
    return "", False


def _extract_acp_tool_output(update: dict[str, Any]) -> str | None:
    chunks: list[str] = []
    content = update.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "content" and isinstance(block.get("content"), dict):
                inner = block["content"]
                if inner.get("type") in (None, "text") and isinstance(
                    inner.get("text"), str
                ):
                    chunks.append(inner["text"])
            elif btype == "text" and isinstance(block.get("text"), str):
                chunks.append(block["text"])
            elif btype == "diff":
                path = block.get("path") or ""
                new_text = block.get("newText")
                old_text = block.get("oldText")
                if isinstance(new_text, str):
                    header = f"--- {path}\n+++ {path}\n" if path else ""
                    if isinstance(old_text, str) and old_text:
                        chunks.append(f"{header}Updated {path or 'file'}")
                    else:
                        chunks.append(f"{header}{new_text[:2000]}")
    if chunks:
        return "\n".join(chunks)
    raw_out = update.get("rawOutput")
    if raw_out is None:
        raw_out = update.get("output")
    if isinstance(raw_out, str):
        return raw_out
    if isinstance(raw_out, dict):
        stdout = raw_out.get("stdout")
        stderr = raw_out.get("stderr")
        if isinstance(stdout, str) or isinstance(stderr, str):
            parts = [s for s in (stdout, stderr) if isinstance(s, str) and s]
            return "\n".join(parts)
        return json.dumps(raw_out, ensure_ascii=False)
    if raw_out is not None:
        return json.dumps(raw_out, ensure_ascii=False)
    return None


def _record_display_text(display_parts: list[dict[str, Any]], delta: str) -> None:
    if not delta:
        return
    if display_parts and display_parts[-1].get("type") == "text":
        display_parts[-1]["text"] = (display_parts[-1].get("text") or "") + delta
    else:
        display_parts.append({"type": "text", "text": delta})


def _record_display_reasoning(display_parts: list[dict[str, Any]], delta: str) -> None:
    if not delta:
        return
    if display_parts and display_parts[-1].get("type") == "reasoning":
        display_parts[-1]["text"] = (display_parts[-1].get("text") or "") + delta
    else:
        display_parts.append({"type": "reasoning", "text": delta})


def _upsert_display_tool(
    display_parts: list[dict[str, Any]],
    tool_call_id: str,
    *,
    tool_name: str | None = None,
    args: str | None = None,
    output: str | None = None,
    state: str | None = None,
    outcome: str | None = None,
) -> None:
    for part in reversed(display_parts):
        if part.get("type") == "tool" and part.get("toolCallId") == tool_call_id:
            if tool_name:
                part["toolName"] = tool_name
            if args:
                part["args"] = args
            if output is not None:
                part["output"] = output
            if state:
                part["state"] = state
            if outcome:
                part["outcome"] = outcome
            return
    entry: dict[str, Any] = {
        "type": "tool",
        "toolCallId": tool_call_id,
        "toolName": tool_name or "tool",
        "args": args or "",
        "state": state or "running",
    }
    if output is not None:
        entry["output"] = output
    if outcome:
        entry["outcome"] = outcome
    display_parts.append(entry)


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


def drain_replayed_updates_to_messages(
    managed: Any,
) -> list[dict[str, Any]]:
    """Drain ``session/update`` notifications replayed during ``session/load`` into Suzent chat rows.

    According to the ACP ``session/load`` specification, the agent replays the
    conversation history via ``session/update`` notifications
    (``user_message_chunk``, ``agent_message_chunk``, ``agent_thought_chunk``,
    ``tool_call``, ``tool_call_update``) before returning the ``session/load``
    response. This function drains ``managed.updates`` and builds a list of
    Suzent message dicts ready for ``db.append_chat_message``.
    """
    messages: list[dict[str, Any]] = []
    cur_role: str | None = None
    user_chunks: list[str] = []
    assistant_text: list[str] = []
    display_parts: list[dict[str, Any]] = []
    started_tools: set[str] = set()
    authoritative_tool_args: set[str] = set()
    last_tool_output: dict[str, str] = {}

    def _flush() -> None:
        nonlocal cur_role
        if cur_role == "user":
            text = "".join(user_chunks).strip()
            if text:
                messages.append({"role": "user", "content": text})
            user_chunks.clear()
        elif cur_role == "assistant":
            text = "".join(assistant_text)
            if text.strip() or display_parts:
                row: dict[str, Any] = {
                    "role": "assistant",
                    "content": text,
                    "model": f"acp/{managed.agent_id}",
                }
                if display_parts:
                    row["parts"] = list(display_parts)
                messages.append(row)
            assistant_text.clear()
            display_parts.clear()
            started_tools.clear()
            authoritative_tool_args.clear()
            last_tool_output.clear()
        cur_role = None

    while not managed.updates.empty():
        try:
            update = managed.updates.get_nowait()
        except asyncio.QueueEmpty:
            break
        if not isinstance(update, dict) or PERMISSION_QUEUE_KEY in update:
            continue

        user_delta = _user_text_from_update(update)
        if user_delta:
            if cur_role != "user":
                _flush()
                cur_role = "user"
            user_chunks.append(user_delta)
            continue

        agent_delta = _text_from_update(update)
        if agent_delta:
            if cur_role != "assistant":
                _flush()
                cur_role = "assistant"
            assistant_text.append(agent_delta)
            _record_display_text(display_parts, agent_delta)
            continue

        thought_delta = _thought_from_update(update)
        if thought_delta:
            if cur_role != "assistant":
                _flush()
                cur_role = "assistant"
            _record_display_reasoning(display_parts, thought_delta)
            continue

        inner = (
            update.get("update") if isinstance(update.get("update"), dict) else update
        )
        kind = str(inner.get("sessionUpdate") or inner.get("type") or "")
        if kind in {"tool_call", "toolCall", "tool_call_update", "toolCallUpdate"}:
            tool_call_id = str(
                inner.get("toolCallId")
                or inner.get("tool_call_id")
                or inner.get("id")
                or ""
            ).strip()
            if not tool_call_id:
                continue
            if cur_role != "assistant":
                _flush()
                cur_role = "assistant"
            has_explicit_name = any(
                isinstance(inner.get(k), str) and inner.get(k).strip()
                for k in ("name", "toolName", "tool_name", "kind")
            )
            tool_name = (
                _infer_acp_tool_name(inner)
                if (tool_call_id not in started_tools or has_explicit_name)
                else None
            )
            started_tools.add(tool_call_id)
            args_str, is_auth = _extract_acp_tool_args(inner)
            if args_str and not is_auth and tool_call_id in authoritative_tool_args:
                args_str = ""
            if args_str and is_auth:
                authoritative_tool_args.add(tool_call_id)
            out_str = _extract_acp_tool_output(inner)
            status = str(inner.get("status") or "").strip().lower()
            is_done = status in ("completed", "done", "succeeded", "success")
            is_failed = status in ("failed", "error", "cancelled", "rejected")
            tool_state = (
                "completed" if (is_done or is_failed or not status) else "running"
            )
            outcome = "failed" if is_failed else None
            prev_out = last_tool_output.get(tool_call_id)
            if out_str is not None:
                last_tool_output[tool_call_id] = out_str
            effective_out = out_str if out_str is not None else prev_out
            _upsert_display_tool(
                display_parts,
                tool_call_id,
                tool_name=tool_name,
                args=args_str or None,
                output=effective_out,
                state=tool_state,
                outcome=outcome,
            )

    _flush()
    return messages


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
        # Only if the dispatch waiter is what woke us. A prompt that raised
        # before the write -- a dead process, a closed stdin -- ends the attempt
        # without the agent ever hearing it, and calling the session live there
        # would take a stop waiting for this run and answer it by cancelling a
        # session that is running nothing.
        deferred_stop = (
            go_live() if go_live is not None and dispatched.is_set() else None
        )
        if deferred_stop:
            # Accepted while the prompt was in flight, so it was never delivered
            # to the session. Now that the agent has the prompt, it can hear it.
            await get_acp_manager().cancel(managed.chat_id)
        while True:
            if prompt_task.done() and managed.updates.empty():
                break
            update_task = asyncio.create_task(managed.updates.get())
            try:
                await asyncio.wait(
                    [update_task, prompt_task], return_when=asyncio.FIRST_COMPLETED
                )
                if not update_task.done():
                    continue
                update = update_task.result()
            finally:
                if not update_task.done():
                    update_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await update_task
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
            display_parts = state.setdefault("display_parts", [])
            started_tools = state.setdefault("started_tools", set())
            last_tool_names = state.setdefault("last_tool_names", {})
            last_tool_args = state.setdefault("last_tool_args", {})
            authoritative_tool_args = state.setdefault("authoritative_tool_args", set())
            last_tool_output = state.setdefault("last_tool_output", {})

            delta = _text_from_update(update)
            if delta:
                state["parts"].append(delta)
                _record_display_text(display_parts, delta)
                yield _sse(
                    {
                        "type": "TEXT_MESSAGE_CONTENT",
                        "messageId": message_id,
                        "delta": delta,
                    }
                )
                continue

            thought_delta = _thought_from_update(update)
            if thought_delta:
                _record_display_reasoning(display_parts, thought_delta)
                yield _sse(
                    {
                        "type": "REASONING_MESSAGE_CHUNK",
                        "messageId": message_id,
                        "delta": thought_delta,
                    }
                )
                continue

            inner = (
                update.get("update")
                if isinstance(update.get("update"), dict)
                else update
            )
            kind = str(inner.get("sessionUpdate") or inner.get("type") or "")

            if kind in {"tool_call", "toolCall", "tool_call_update", "toolCallUpdate"}:
                tool_call_id = str(
                    inner.get("toolCallId")
                    or inner.get("tool_call_id")
                    or inner.get("id")
                    or ""
                ).strip()
                if tool_call_id:
                    has_explicit_name = any(
                        isinstance(inner.get(k), str) and inner.get(k).strip()
                        for k in ("name", "toolName", "tool_name", "kind")
                    )
                    tool_name = (
                        _infer_acp_tool_name(inner)
                        if (tool_call_id not in started_tools or has_explicit_name)
                        else None
                    )
                    args_str, is_authoritative_args = _extract_acp_tool_args(inner)
                    if (
                        args_str
                        and not is_authoritative_args
                        and tool_call_id in authoritative_tool_args
                    ):
                        # Do not overwrite previously received rawInput/diff
                        # arguments with a metadata-only fallback (e.g. path or
                        # title on a completion update).
                        args_str = ""
                    if args_str and is_authoritative_args:
                        authoritative_tool_args.add(tool_call_id)
                    out_str = _extract_acp_tool_output(inner)
                    status = str(inner.get("status") or "").strip().lower()

                    is_new_tool = tool_call_id not in started_tools
                    name_changed = bool(
                        tool_name and last_tool_names.get(tool_call_id) != tool_name
                    )
                    if tool_name:
                        last_tool_names[tool_call_id] = tool_name
                    args_changed = bool(
                        args_str and last_tool_args.get(tool_call_id) != args_str
                    )
                    had_prev_args = bool(last_tool_args.get(tool_call_id))
                    if args_changed:
                        last_tool_args[tool_call_id] = args_str

                    if is_new_tool:
                        started_tools.add(tool_call_id)
                        yield _sse(
                            {
                                "type": "TOOL_CALL_START",
                                "toolCallId": tool_call_id,
                                "toolCallName": tool_name or "tool",
                            }
                        )
                    elif name_changed or (args_changed and had_prev_args):
                        # Re-emit TOOL_CALL_START when the tool name was refined
                        # or when a new argument snapshot replaces an earlier one.
                        yield _sse(
                            {
                                "type": "TOOL_CALL_START",
                                "toolCallId": tool_call_id,
                                "toolCallName": last_tool_names.get(tool_call_id) or "",
                            }
                        )
                    if args_changed:
                        yield _sse(
                            {
                                "type": "TOOL_CALL_ARGS",
                                "toolCallId": tool_call_id,
                                "delta": args_str,
                            }
                        )

                    is_done = status in ("completed", "done", "succeeded", "success")
                    is_failed = status in ("failed", "error", "cancelled", "rejected")
                    tool_state = "completed" if (is_done or is_failed) else "running"
                    outcome = "failed" if is_failed else None
                    prev_out = last_tool_output.get(tool_call_id)
                    if out_str is not None:
                        last_tool_output[tool_call_id] = out_str
                    effective_out = out_str if out_str is not None else prev_out
                    _upsert_display_tool(
                        display_parts,
                        tool_call_id,
                        tool_name=tool_name,
                        args=args_str or None,
                        output=effective_out,
                        state=tool_state,
                        outcome=outcome,
                    )

                    if is_done or is_failed:
                        result_payload = (
                            effective_out
                            if effective_out is not None
                            else ("Failed" if is_failed else "Completed")
                        )
                        if is_failed and not result_payload.lstrip().startswith("{"):
                            result_payload = json.dumps(
                                {
                                    "success": False,
                                    "error_code": "tool_failed",
                                    "message": result_payload,
                                },
                                ensure_ascii=False,
                            )
                        yield _sse(
                            {
                                "type": "TOOL_CALL_RESULT",
                                "toolCallId": tool_call_id,
                                "content": result_payload,
                            }
                        )
                        if is_failed:
                            yield _sse(
                                {
                                    "type": "CUSTOM",
                                    "name": "tool_call_outcome",
                                    "value": {
                                        "toolCallId": tool_call_id,
                                        "outcome": "failed",
                                    },
                                }
                            )
                    elif out_str and out_str != prev_out:
                        delta_out = (
                            out_str[len(prev_out) :]
                            if (prev_out and out_str.startswith(prev_out))
                            else out_str
                        )
                        yield _sse(
                            {
                                "type": "CUSTOM",
                                "name": "shell_output_delta",
                                "value": {
                                    "toolCallId": tool_call_id,
                                    "delta": delta_out,
                                },
                            }
                        )
                    continue

            if kind == "plan" and isinstance(inner.get("entries"), list):
                plan_lines = []
                for entry in inner["entries"]:
                    if isinstance(entry, dict) and entry.get("content"):
                        st = str(entry.get("status") or "")
                        mark = (
                            "x"
                            if st == "completed"
                            else "~"
                            if st == "in_progress"
                            else " "
                        )
                        plan_lines.append(f"- [{mark}] {entry['content']}")
                if plan_lines:
                    plan_text = "\n" + "\n".join(plan_lines) + "\n"
                    _record_display_reasoning(display_parts, plan_text)
                    yield _sse(
                        {
                            "type": "REASONING_MESSAGE_CHUNK",
                            "messageId": message_id,
                            "delta": plan_text,
                        }
                    )
                    continue

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
    display_parts = state.setdefault("display_parts", [])
    for part in display_parts:
        if part.get("type") == "tool" and part.get("state") == "running":
            part["state"] = "completed"
    if not state["parts"]:
        fallback = result.get("text") or result.get("message")
        if isinstance(fallback, str) and fallback:
            state["parts"].append(fallback)
            _record_display_text(display_parts, fallback)
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
    prewritten: bool = False,
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
        chat_id, message, config_override, replay=replay, prewritten=prewritten
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
    system_reminders: Sequence[str] | None = None,
    system_preamble: str | None = None,
    replay: Any | None = None,
    prewritten: bool = False,
) -> AsyncGenerator[str, None]:
    """Run one ACP turn, claiming the replay's persistence contract for it.

    *system_reminders* are runtime context for the agent, assembled by the same
    builder the native runtime uses, so an ACP turn gets the same budget and the
    same trigger row as a native one.

    The contract is claimed here rather than inside the turn so that it covers
    the turn's whole lifetime. A replay with no persistence future reports
    `persisted` as True the moment it closes, and everything below — the chat
    lookup, sanitizing the prompt, the agent itself — can fail or return early;
    any of those exits would otherwise end the stream with
    STREAM_END{persisted:true} for a turn that was never stored, which the
    client trusts enough to replace what it is showing.
    """
    persistence = _attach_persistence(replay)
    reminder = await _assemble_reminder(chat_id, message, system_reminders)

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
        stored = _persist_stopped_prompt(
            chat_id,
            message,
            runtime_authored,
            files,
            reminder=reminder,
            prewritten=prewritten,
        )
        _resolve_persistence(persistence, stored)
        yield _sse(
            {"type": "RUN_ERROR", "message": pending_stop, "code": "stream_stopped"}
        )
        return

    from suzent.core.chat_status import begin_turn, schedule_judgement

    status_turn = begin_turn(chat_id)
    reply = ""
    failed = False
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
            reminder=reminder,
            system_preamble=system_preamble,
            prewritten=prewritten,
        ):
            event = _parse_sse(chunk)
            if event.get("type") == "TEXT_MESSAGE_CONTENT":
                reply += str(event.get("delta") or "")
            elif event.get("type") == "RUN_ERROR":
                failed = True
            yield chunk
        if not failed:
            # With the reminder, as the native runtime judges it: on a
            # reminder-only turn that block is the whole request.
            await schedule_judgement(
                chat_id, _with_reminder(message, reminder), reply, status_turn
            )
    finally:
        # Anything that did not reach the assistant append — an early return, an
        # exception, a cancelled subscription — persisted nothing, and says so.
        _resolve_persistence(persistence, False)


async def _assemble_reminder(
    chat_id: str, message: str, system_reminders: Sequence[str] | None
) -> str | None:
    """Build the turn's reminder block the way the native runtime does.

    Stateless, so no global or per-turn hooks run: their output (skill hints,
    plan state, memory retrieval) points at Suzent's own tools, which an
    external agent cannot call. Only the caller's reminders are delivered.

    The trigger rule mirrors ``ChatProcessor.process_turn``: a reminder-only
    turn is shown as the reminders it delivered; a turn the user typed is shown
    as what they typed.
    """
    if not system_reminders:
        return None
    from suzent.core.system_reminder import build_combined_reminder

    display_trigger = (
        None
        if message and message.strip()
        else [r.strip() for r in system_reminders if r and r.strip()]
    )
    return await build_combined_reminder(
        chat_id,
        SimpleNamespace(stateless=True, chat_id=chat_id),
        adhoc_reminders=list(system_reminders),
        display_trigger=display_trigger,
    )


def _derive_user_row(
    message: str, runtime_authored: bool, reminder: str | None = None
) -> tuple[str, str, str]:
    """Sanitize a prompt and derive the transcript row it should leave.

    Returns the sanitized user text, the role to store it under, and the
    content to store. The *reminder* is not part of the returned text: it is
    appended after any file context, as the native runtime appends it after the
    user's message. Shared with the stopped-before-it-started path, which
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
    # The row is read back out of the block that is sent, as
    # trigger_rows_for_snapshot does, so it records what the agent was shown.
    rendered = _with_reminder(message, reminder)

    display_trigger = extract_system_reminder_display_trigger(rendered)
    visible_user_message = strip_system_reminders(rendered)
    persisted_role = (
        "system_triggered" if display_trigger and not visible_user_message else "user"
    )
    persisted_content = (
        display_trigger
        if persisted_role == "system_triggered"
        else visible_user_message
    )
    return message, persisted_role, persisted_content


def _with_reminder(message: str, reminder: str | None) -> str:
    """Append the reminder block after the prompt, where the native runtime puts it."""
    if not reminder:
        return message
    return f"{message}\n\n{reminder}" if message and message.strip() else reminder


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
    *,
    prewritten: bool = False,
) -> bool:
    """Store the user's row unless the route already pre-wrote it.

    /chat/send pre-writes it so the UI has something to show before the first
    token arrives; the direct /chat stream does not. Returns whether the row is
    in the transcript afterwards, which is what a caller resolving the
    persistence contract has to promise.

    `prewritten` is the route saying it wrote that row, and nothing else stands
    in for it. Inferring it from the message -- same text, same attachments as
    the last row -- reads a prompt the user deliberately sent again after
    stopping the first one as a row already there, and drops it while promising
    the reload holds it.

    Attachments are part of that row: a message can be nothing but files, and a
    row stored without them is not the message the user sent.
    """
    attachments = _display_files(files)
    if not content.strip() and not attachments:
        return True
    if (
        existing
        and prewritten
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
    *,
    reminder: str | None = None,
    prewritten: bool = False,
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
        _, role, content = _derive_user_row(message, runtime_authored, reminder)
        return _append_user_row(
            db,
            chat_id,
            list(chat.messages or []),
            role,
            content,
            files,
            prewritten=prewritten,
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
    reminder: str | None = None,
    system_preamble: str | None = None,
    replay: Any | None = None,
    prewritten: bool = False,
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
        message, runtime_authored, reminder
    )
    file_context = _build_acp_file_context(file_mentions, files)
    file_context += build_chat_mention_context(message or "", external_agent=True)
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
    # After the sanitizing above, not before it: the block carries this
    # process's token and must survive, while everything ahead of it is the
    # caller's text and must not gain that status.
    message = _with_reminder(message, reminder)

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
        if getattr(managed, "restored", False):
            # session/load replays prior turns into managed.updates; drain them
            # before _stream_prompt runs so prior history is never concatenated
            # into the new assistant turn.
            while not managed.updates.empty():
                try:
                    managed.updates.get_nowait()
                except asyncio.QueueEmpty:
                    break
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
            db,
            chat_id,
            existing,
            persisted_role,
            persisted_content,
            files,
            prewritten=prewritten,
        )
        if persisted_role == "system_triggered" and stored_prompt:
            # The client reloads the display log the moment the stream opens,
            # before this row lands, so the stream announces it — the same
            # event the native runtime sends for its pre-saved trigger rows.
            yield _sse(
                {
                    "type": "CUSTOM",
                    "name": "incoming_message",
                    "value": {"content": persisted_content, "persisted": True},
                }
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
            replay.prompt_in_flight = True
            return _claim_pending_stop(replay)

        def _go_idle() -> None:
            """The prompt is back; the session is no longer running this turn.

            What is left -- the assistant row, the title lookup -- cannot be
            cancelled, and the session may already be carrying somebody else's
            prompt. A stop arriving now is answered as the miss it is rather
            than by cancelling whatever the session happens to be running.
            """
            if replay is not None:
                replay.prompt_in_flight = False

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
        # In a finally: the prompt can fail after it was dispatched -- a
        # JSON-RPC error from a live agent -- and that raises through here.
        # The session is idle either way, and a mark left standing offers it
        # to the next stop for a run whose prompt is long gone.
        try:
            async for event in _stream_prompt(
                managed, _prompt, message_id, state, _go_live
            ):
                yield event
        finally:
            _go_idle()

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
                replay.prompt_in_flight = False
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
            try:
                async for event in _stream_prompt(
                    managed, _prompt, message_id, state, _go_live
                ):
                    yield event
            finally:
                _go_idle()

        text = "".join(state["parts"])
        display_parts = state.get("display_parts") or []
        has_tool_activity = any(part.get("type") == "tool" for part in display_parts)
        stop_reason = state.get("stop_reason") or ""
        turn_failed = bool(state.get("error")) or (stop_reason not in ("", "end_turn"))
        yield _sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})
        message_open = False
        if not text.strip() and (turn_failed or not has_tool_activity):
            if stop_reason == "cancelled":
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
                stored_activity = True
                if display_parts:
                    stored_activity = db.append_chat_message(
                        chat_id,
                        {
                            "role": "assistant",
                            "content": text,
                            "model": f"acp/{managed.agent_id}",
                            "parts": display_parts,
                        },
                    )
                _resolve_persistence(persistence, stored_prompt and stored_activity)
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
        row: dict[str, Any] = {
            "role": "assistant",
            "content": text,
            "model": f"acp/{managed.agent_id}",
        }
        if display_parts:
            row["parts"] = display_parts
        stored = db.append_chat_message(
            chat_id,
            row,
        )
        # Both rows or neither, as far as the client is concerned: an answer
        # stored without the prompt that asked for it is a transcript the reload
        # would come back holding, so a turn that lost the prompt row must not
        # tell the client its reload is trustworthy.
        _resolve_persistence(persistence, stored_prompt and stored is not False)
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
        if isinstance(exc, ACPError) and exc.auth_required:
            await get_acp_manager().close(chat_id)
            yield _sse(
                {
                    "type": "RUN_ERROR",
                    "code": "acp_auth_required",
                    "message": "Sign in under Settings → ACP Agents, then retry this task. "
                    "Your saved session ID has been preserved.",
                }
            )
        else:
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
    system_reminders: Sequence[str] | None = None,
    system_preamble: str | None = None,
    errors_out: list[str] | None = None,
) -> str:
    """Run one ACP turn and return its text.

    ``errors_out`` collects each ``RUN_ERROR`` message, so a caller that only
    reads the text can still tell a failed turn from a silent one.
    """
    text = ""
    async for chunk in stream_acp_turn(
        chat_id,
        message,
        config_override,
        runtime_authored=runtime_authored,
        system_reminders=system_reminders,
        system_preamble=system_preamble,
        replay=getattr(stream_queue, "replay", None),
    ):
        if stream_queue is not None:
            await stream_queue.put(chunk)
        event = _parse_sse(chunk)
        if event.get("type") == "TEXT_MESSAGE_CONTENT":
            text += str(event.get("delta") or "")
        elif event.get("type") == "RUN_ERROR" and errors_out is not None:
            errors_out.append(str(event.get("message") or "unknown error"))
    return text
