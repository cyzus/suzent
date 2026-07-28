from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def _display_message_text(message: dict[str, Any]) -> str:
    """Return the agent-visible text from a persisted display message."""
    parts = message.get("parts")
    if isinstance(parts, list):
        text_parts = [
            str(part.get("text") or "")
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        if any(text_parts):
            return "".join(text_parts)

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item) for item in content if isinstance(item, str))
    return ""


def _state_from_display_messages(messages: list[dict[str, Any]]) -> bytes | None:
    """Build a text-only agent history when no persisted model history is available."""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    from suzent.core.agent_serializer import serialize_state

    history: list[Any] = []
    for message in messages:
        role = message.get("role")
        text = _display_message_text(message).strip()
        if not text:
            continue
        if role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
        elif role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=text)]))
    return serialize_state(history) if history else None


def _agent_state_at_display_point(
    agent_state: bytes | None,
    display_messages: list[dict[str, Any]],
    turn_index: int,
) -> bytes | None:
    """Truncate persisted model history at the selected assistant display row."""
    from pydantic_ai.messages import ModelResponse

    from suzent.core.agent_serializer import deserialize_state, serialize_state

    selected_messages = display_messages[:turn_index]
    selected_assistant_count = sum(
        message.get("role") == "assistant" for message in selected_messages
    )
    state = deserialize_state(agent_state) if agent_state else None
    if state and selected_assistant_count:
        history = state.get("message_history") or []
        assistant_count = 0
        for index, message in enumerate(history):
            if not isinstance(message, ModelResponse):
                continue
            assistant_count += 1
            if assistant_count == selected_assistant_count:
                return serialize_state(
                    history[: index + 1],
                    model_id=state.get("model_id"),
                    tool_names=state.get("tool_names"),
                )

    return _state_from_display_messages(selected_messages)


def _raw_index_at_logical_display_point(
    messages: list[dict[str, Any]],
    logical_index: int,
) -> int:
    """Map a frontend-rendered message boundary back to the raw display log."""
    boundaries: list[tuple[str, int]] = []
    assistant_end: int | None = None
    awaiting_tool_continuation = False

    def flush_assistant() -> None:
        nonlocal assistant_end, awaiting_tool_continuation
        if assistant_end is not None:
            boundaries.append(("assistant", assistant_end))
        assistant_end = None
        awaiting_tool_continuation = False

    for index, message in enumerate(messages):
        role = message.get("role")
        raw_end = index + 1
        if role == "user":
            content = message.get("content")
            has_content = isinstance(content, str) and bool(content.strip())
            if (
                not has_content
                and not message.get("images")
                and not message.get("files")
            ):
                continue
            flush_assistant()
            boundaries.append(("user", raw_end))
        elif role in {"system_triggered", "trigger"}:
            flush_assistant()
            boundaries.append(("system_triggered", raw_end))
        elif role == "assistant":
            if assistant_end is None:
                assistant_end = raw_end
                awaiting_tool_continuation = False
            elif awaiting_tool_continuation:
                assistant_end = raw_end
                awaiting_tool_continuation = False
            else:
                flush_assistant()
                assistant_end = raw_end
            if message.get("tool_calls"):
                awaiting_tool_continuation = True
        elif role == "tool":
            if assistant_end is None:
                assistant_end = raw_end
            else:
                assistant_end = raw_end
            awaiting_tool_continuation = True
        else:
            flush_assistant()
            boundaries.append((str(role or "unknown"), raw_end))

    flush_assistant()
    if not 1 <= logical_index <= len(boundaries):
        raise ValueError("turn_index is outside the rendered message history")
    role, raw_index = boundaries[logical_index - 1]
    if role != "assistant":
        raise ValueError("Conversation branches must start from an assistant message")
    return raw_index


def fork_chat(
    source_chat_id: str,
    *,
    title: str | None = None,
    turn_index: int | None = None,
) -> tuple[str, list[str]]:
    """Create an independent conversation branch without changing workspace files."""
    from suzent.config import CONFIG
    from suzent.database import get_database

    db = get_database()
    source = db.get_chat(source_chat_id)
    if source is None:
        raise ValueError(f"Chat not found: {source_chat_id}")

    raw_turn_index = None
    branch_agent_state = source.agent_state
    if turn_index is not None:
        raw_turn_index = _raw_index_at_logical_display_point(
            list(source.messages or []),
            turn_index,
        )
        branch_agent_state = _agent_state_at_display_point(
            source.agent_state,
            list(source.messages or []),
            raw_turn_index,
        )

    new_chat_id = db.clone_chat_to_point(
        source_chat_id,
        new_title=title,
        up_to_message_index=raw_turn_index,
    )
    branch = db.get_chat(new_chat_id)
    branch_config = dict(branch.config or {}) if branch else {}
    branch_config.update(
        {
            "forked_from_chat_id": source_chat_id,
            "forked_from_chat_title": source.title,
            "forked_from_message_index": turn_index
            if turn_index is not None
            else len(source.messages or []),
        }
    )
    db.update_chat(new_chat_id, config=branch_config)

    history_root = Path(CONFIG.sandbox_data_path) / "file-history"
    source_history = history_root / source_chat_id
    new_history = history_root / new_chat_id
    if source_history.exists():
        shutil.copytree(source_history, new_history, dirs_exist_ok=True)

    if turn_index is not None:
        branch = db.get_chat(new_chat_id)
        db.rewrite_chat_messages(
            new_chat_id,
            list(branch.messages or []) if branch else [],
            agent_state=branch_agent_state,
        )

    return new_chat_id, []
