from __future__ import annotations

import json
import re
from typing import Any

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core.system_reminder import iter_reminder_fragments, strip_system_reminders


MAX_TRANSCRIPT_CHARS = 12_000
MAX_LINE_CHARS = 2_000
MAX_REQUEST_CHARS = 4_000

#: Tools whose arguments are instructions the agent writes for another agent.
#: The reviewer read "do not edit source files" in a verifier's brief as the
#: user's rule for the agent itself and blocked the agent's own edits.
DELEGATION_TOOLS = frozenset({"agent"})

#: First line of a message the agent inbox delivers. The runtime writes the
#: sender's chat ID last, so the final parenthesised group is the sender even
#: when a chat title carries brackets of its own.
_AGENT_MESSAGE_HEADER_RE = re.compile(r"\[Agent message from [^\n]* \(([^()\n]*)\)\]")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _prompt_text(part: UserPromptPart) -> str:
    content = part.content
    if isinstance(content, str):
        text = content
    else:
        text = "".join(item for item in content if isinstance(item, str))
    return text


def _user_text(part: UserPromptPart) -> str:
    return strip_system_reminders(_prompt_text(part)).strip()


def _delegated_task(fragment: str, delegator_chat_ids: frozenset[str]) -> str:
    """The brief in a delegator's agent message, or "" for any other fragment."""
    header, _, body = fragment.partition("\n")
    match = _AGENT_MESSAGE_HEADER_RE.fullmatch(header.strip())
    if match is None or match.group(1) not in delegator_chat_ids:
        return ""
    return body.strip()


def _runtime_text(
    part: UserPromptPart, delegator_chat_ids: frozenset[str]
) -> tuple[str, str]:
    """A part's authenticated reminders, split into (delegated task, the rest).

    A worker started by Regent has no user words of its own: Regent's brief is
    its whole request. Left as plain runtime context, which the reviewer is told
    authorizes nothing, it read every action the brief asked for as unrequested.
    """
    tasks: list[str] = []
    runtime: list[str] = []
    for block in iter_reminder_fragments(_prompt_text(part), authenticated_only=True):
        for fragment in block:
            fragment = fragment.strip()
            if task := _delegated_task(fragment, delegator_chat_ids):
                tasks.append(task)
            elif fragment:
                runtime.append(fragment)
    return "\n\n".join(tasks), "\n\n".join(runtime)


def _is_summary(text: str) -> bool:
    from suzent.core.context_compressor import is_compaction_summary_text

    return is_compaction_summary_text(text)


def _args_text(part: ToolCallPart) -> str:
    args = part.args
    if isinstance(args, str):
        return args
    return json.dumps(args, ensure_ascii=False, default=str)


def _render_part(part: Any) -> str:
    match part:
        case UserPromptPart():
            text = _user_text(part)
            if _is_summary(text):
                return f"EARLIER CONTEXT SUMMARY: {text}"
            return f"USER: {text}" if text else ""
        case TextPart():
            return f"AGENT: {part.content}" if part.content.strip() else ""
        case ToolCallPart() if part.tool_name in DELEGATION_TOOLS:
            return (
                "AGENT DELEGATED TO A SUB-AGENT (the agent's brief for that "
                "sub-agent; it constrains the sub-agent only, not the agent or "
                f"the user's request): {_args_text(part)}"
            )
        case ToolCallPart():
            return f"AGENT CALLED {part.tool_name}: {_args_text(part)}"
        case ToolReturnPart():
            return f"TOOL RESULT {part.tool_name}: {part.model_response_str()}"
        case RetryPromptPart():
            return f"TOOL ERROR {part.tool_name or ''}: {part.model_response()}"
        case _:
            return ""


def _inline(text: str) -> str:
    # Source content must not create a new line impersonating another author.
    return text.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def _render_message(message: Any, delegator_chat_ids: frozenset[str]) -> str:
    if not isinstance(message, (ModelRequest, ModelResponse)):
        return "UNATTRIBUTED CONTEXT: " + _inline(str(message))
    lines = []
    for part in message.parts:
        lines.append(_render_part(part))
        if isinstance(part, UserPromptPart):
            task, runtime = _runtime_text(part, delegator_chat_ids)
            if task:
                lines.append(f"DELEGATED TASK: {task}")
            if runtime:
                lines.append(f"RUNTIME CONTEXT: {runtime}")
    return "\n".join(_clip(_inline(line), MAX_LINE_CHARS) for line in lines if line)


def latest_user_request(messages: list[Any]) -> str:
    """The user's most recent words, however far back the tool calls push them."""
    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in reversed(message.parts):
            if isinstance(part, UserPromptPart):
                text = _user_text(part)
                if text and not _is_summary(text):
                    return text
    return ""


def _latest_runtime_context(
    messages: list[Any], delegator_chat_ids: frozenset[str]
) -> str:
    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in reversed(message.parts):
            if not isinstance(part, UserPromptPart):
                continue
            user = _user_text(part)
            if _is_summary(user):
                continue
            task, runtime = _runtime_text(part, delegator_chat_ids)
            if user or task or runtime:
                return runtime
    return ""


def _latest_delegated_task(
    messages: list[Any], delegator_chat_ids: frozenset[str]
) -> str:
    """The newest brief from a delegator, which later runtime notes don't replace."""
    if not delegator_chat_ids:
        return ""
    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in reversed(message.parts):
            if isinstance(part, UserPromptPart):
                task, _ = _runtime_text(part, delegator_chat_ids)
                if task:
                    return task
    return ""


def compact_transcript(
    messages: list[Any], *, delegator_chat_ids: frozenset[str] = frozenset()
) -> str:
    """Project recent conversation context into a bounded classifier transcript.

    Every line names who wrote it, and the user's current request leads even
    when a long tool run has pushed it out of the recent window: without it the
    only instructions the reviewer could see were ones the agent wrote itself.
    ``delegator_chat_ids`` are the chats whose agent messages assign this
    session its task, shown as DELEGATED TASK rather than runtime context.
    """
    headers = [
        f"{label}: {_clip(_inline(text), MAX_REQUEST_CHARS)}"
        for label, text in (
            ("CURRENT USER REQUEST", latest_user_request(messages)),
            (
                "CURRENT DELEGATED TASK",
                _latest_delegated_task(messages, delegator_chat_ids),
            ),
            (
                "CURRENT RUNTIME CONTEXT",
                _latest_runtime_context(messages, delegator_chat_ids),
            ),
        )
        if text
    ]
    header = _clip("\n\n".join(headers), MAX_TRANSCRIPT_CHARS)
    remaining = MAX_TRANSCRIPT_CHARS - len(header)
    parts: list[str] = []
    for message in reversed(messages[-20:]):
        text = _render_message(message, delegator_chat_ids)
        separator_size = 2 if header or parts else 0
        available = max(0, remaining - separator_size)
        text = _clip(text, available) if available else ""
        if text:
            parts.append(text)
            remaining -= len(text) + separator_size
        if remaining <= 0:
            break
    return "\n\n".join([header, *reversed(parts)] if header else reversed(parts))
