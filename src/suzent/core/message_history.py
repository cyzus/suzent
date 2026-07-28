"""Validation and repair helpers for model-facing message history."""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)


def _is_tool_result_part(part: Any) -> bool:
    return isinstance(part, ToolReturnPart) or (
        isinstance(part, RetryPromptPart) and bool(part.tool_name)
    )


def safe_tool_history_tail_start(messages: list[Any], desired_start: int) -> int:
    """Move a tail boundary left until it no longer orphans tool results."""

    start = max(0, min(desired_start, len(messages)))
    while start > 0:
        calls_in_tail = {
            part.tool_call_id
            for message in messages[start:]
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, ToolCallPart) and part.tool_call_id
        }
        returns_in_tail = {
            part.tool_call_id
            for message in messages[start:]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if _is_tool_result_part(part) and part.tool_call_id
        }
        orphan_ids = returns_in_tail - calls_in_tail
        if not orphan_ids:
            break

        matching_indexes = [
            index
            for index, message in enumerate(messages[:start])
            if isinstance(message, ModelResponse)
            and any(
                isinstance(part, ToolCallPart) and part.tool_call_id in orphan_ids
                for part in message.parts
            )
        ]
        if not matching_indexes:
            break
        start = min(matching_indexes)

    return start


def strip_tool_interactions(messages: list[Any]) -> tuple[list[Any], int]:
    """Remove tool protocol parts as a last-resort provider recovery.

    Pydantic AI already repairs regular call/result pairing. This more lossy
    fallback is only for provider-specific ordering errors that remain after its
    built-in repair. Text and user prompts remain, so the agent can continue with
    reduced context.
    """

    stripped: list[Any] = []
    removed = 0
    for message in messages:
        if isinstance(message, ModelResponse):
            parts = [
                part for part in message.parts if not isinstance(part, ToolCallPart)
            ]
        elif isinstance(message, ModelRequest):
            parts = [part for part in message.parts if not _is_tool_result_part(part)]
        else:
            stripped.append(message)
            continue

        removed += len(message.parts) - len(parts)
        if parts:
            stripped.append(
                message
                if len(parts) == len(message.parts)
                else dataclasses.replace(message, parts=parts)
            )

    return stripped, removed


def is_tool_history_protocol_error(error: Exception) -> bool:
    """Return whether an exception is the repairable OpenAI-compatible 400."""

    status_code = getattr(error, "status_code", None)
    text = str(error).lower()
    return (
        (status_code in (None, 400))
        and "role 'tool'" in text
        and "preceding message" in text
        and "tool_calls" in text
    )
