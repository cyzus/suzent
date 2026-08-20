"""
Bridge between an A2A task and a Suzent agent turn.

An inbound ``message/send`` or ``message/stream`` lands here. We run the normal
``ChatProcessor`` turn — the same one the local UI and the Suzent peer channel
use — and translate its AG-UI event stream into A2A task events:

    AG-UI TEXT_MESSAGE_CONTENT  →  TaskArtifactUpdateEvent (streamed text)
    AG-UI RUN_ERROR             →  TaskStatusUpdateEvent(failed)
    generator completes         →  TaskStatusUpdateEvent(completed)

The A2A ``contextId`` *is* a Suzent chat id, so a remote agent that keeps using
the same contextId resumes a real conversation with real history, and the turn
shows up in this device's own UI like any other session.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from suzent.a2a.tasks import TaskStore, TaskTransitionError
from suzent.a2a.types import (
    Artifact,
    Message,
    Role,
    TaskState,
    TextPart,
)
from suzent.logger import get_logger

logger = get_logger(__name__)

# A2A contexts we accept map onto chat ids in a dedicated namespace, so a remote
# caller can never address an arbitrary local chat by guessing its id.
CONTEXT_PREFIX = "a2a"
_SAFE_CONTEXT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class A2AExecutionError(RuntimeError):
    """Raised when a task cannot be started (bad context, agent unavailable)."""


def context_chat_id(agent_key: str, context_id: str | None) -> str:
    """Map an A2A contextId onto a namespaced local chat id.

    ``agent_key`` is the authenticated caller's identity — contexts are scoped
    per caller so two remote agents can't read each other's conversation by
    reusing a contextId, mirroring ``_peer_chat_id`` in the Suzent channel.
    """
    root = f"{CONTEXT_PREFIX}:{agent_key}"
    if not context_id:
        return f"{root}:{uuid.uuid4().hex[:12]}"
    candidate = str(context_id).strip()
    if candidate == root or candidate.startswith(f"{root}:"):
        return candidate
    if not _SAFE_CONTEXT.match(candidate):
        raise A2AExecutionError("Invalid contextId")
    return f"{root}:{candidate}"


def _extract_text_delta(chunk: str) -> str:
    """Pull the text delta out of one AG-UI SSE frame, if it carries one."""
    if not chunk.startswith("data: "):
        return ""
    try:
        event = json.loads(chunk[6:].strip() or "{}")
    except ValueError:
        return ""
    if event.get("type") == "TEXT_MESSAGE_CONTENT":
        return str(event.get("delta") or "")
    return ""


def _extract_error(chunk: str) -> str | None:
    if not chunk.startswith("data: "):
        return None
    try:
        event = json.loads(chunk[6:].strip() or "{}")
    except ValueError:
        return None
    if event.get("type") == "RUN_ERROR":
        return str(event.get("message") or "The remote turn failed")
    return None


async def run_task(
    *,
    store: TaskStore,
    task_id: str,
    chat_id: str,
    content: str,
    caller_label: str,
    created_now_holder: dict[str, bool] | None = None,
) -> None:
    """Execute one A2A task to a terminal state, publishing events as it goes.

    Always settles the task: any unexpected failure lands as ``failed`` rather
    than leaving a task stuck in ``working`` forever.
    """
    from suzent.agent_manager import build_agent_config
    from suzent.config import CONFIG
    from suzent.core.chat_processor import ChatProcessor
    from suzent.database import get_database

    accumulated: list[str] = []
    try:
        await store.set_state(task_id, TaskState.working)

        db = get_database()
        created_now = db.ensure_channel_chat(
            chat_id,
            title=f"⇄ {caller_label}",
            platform="a2a",
            config_extra={"sender_id": caller_label, "sender_name": caller_label},
        )
        if created_now_holder is not None:
            created_now_holder["created"] = created_now

        config_override = build_agent_config({}, require_social_tool=False)
        # A remote A2A caller cannot answer an interactive approval prompt, so
        # the turn runs headless — same reasoning as the Suzent peer channel.
        config_override["interaction_profile"] = "headless"
        config_override["permission_mode"] = "auto"

        attribution = (
            f"This turn was triggered by the remote agent '{caller_label}' over the "
            "A2A (Agent2Agent) protocol — not by the local user. It is another "
            "agent, not a human: answer directly and completely, and do not ask "
            "follow-up questions unless you genuinely cannot proceed."
        )

        processor = ChatProcessor()
        generator = processor.process_turn(
            chat_id=chat_id,
            user_id=CONFIG.user_id,
            message_content=content,
            config_override=config_override,
            system_reminders=[attribution],
        )

        artifact_id = uuid.uuid4().hex
        failure: str | None = None
        async for chunk in generator:
            error = _extract_error(chunk)
            if error:
                failure = error
                break
            delta = _extract_text_delta(chunk)
            if not delta:
                continue
            accumulated.append(delta)
            # Stream incrementally: append=True after the first chunk so the
            # client concatenates rather than replaces.
            await store.add_artifact(
                task_id,
                Artifact(
                    artifact_id=artifact_id,
                    name="response",
                    parts=[TextPart(text=delta)],
                ),
                append=len(accumulated) > 1,
            )

        if failure:
            await store.set_state(
                task_id,
                TaskState.failed,
                message=Message(
                    message_id=uuid.uuid4().hex,
                    role=Role.agent,
                    parts=[TextPart(text=failure)],
                ),
            )
            return

        final_text = "".join(accumulated).strip()
        await store.set_state(
            task_id,
            TaskState.completed,
            message=Message(
                message_id=uuid.uuid4().hex,
                role=Role.agent,
                parts=[TextPart(text=final_text or "(no output)")],
            ),
        )
    except asyncio.CancelledError:
        # Cooperative cancellation: tasks/cancel already moved the state, so only
        # settle it here if something else cancelled us.
        current = store.get(task_id)
        if current and not current.status.state.is_terminal:
            try:
                await store.set_state(task_id, TaskState.canceled)
            except TaskTransitionError:
                pass
        raise
    except Exception as exc:
        logger.error("A2A task {} failed: {}", task_id, exc)
        current = store.get(task_id)
        if current and not current.status.state.is_terminal:
            try:
                await store.set_state(
                    task_id,
                    TaskState.failed,
                    message=Message(
                        message_id=uuid.uuid4().hex,
                        role=Role.agent,
                        parts=[TextPart(text=f"{type(exc).__name__}: {exc}")],
                    ),
                )
            except TaskTransitionError:
                pass
