"""
Sub-agent runner: spawns isolated background agent tasks with tool whitelisting
and parent-session notification on completion.

Architecture mirrors SchedulerBrain._execute_job but is triggered by the agent
at runtime (via spawn_subagent tool) rather than a cron schedule.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.core.stream_registry import (
    register_background_stream,
    unregister_background_stream,
    background_queues,
    get_active_stream_queue,
)

logger = get_logger(__name__)

# ─── In-memory task registry ─────────────────────────────────────────────────


@dataclass
class SubAgentTask:
    task_id: str
    parent_chat_id: str
    description: str
    tools_allowed: list[str]
    status: str = "queued"  # queued | running | completed | failed
    result_summary: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    chat_id: str = ""  # isolated chat created for this sub-agent
    cwd: Optional[str] = None  # working directory override for bash execution


# Global registry: task_id -> SubAgentTask
_tasks: Dict[str, SubAgentTask] = {}
_tasks_lock = asyncio.Lock()


def get_task(task_id: str) -> Optional[SubAgentTask]:
    return _tasks.get(task_id)


def list_active_tasks() -> list[SubAgentTask]:
    return [t for t in _tasks.values() if t.status in ("queued", "running")]


def list_all_tasks(parent_chat_id: str = None) -> list[SubAgentTask]:
    tasks = list(_tasks.values())
    if parent_chat_id:
        tasks = [t for t in tasks if t.parent_chat_id == parent_chat_id]
    return sorted(tasks, key=lambda t: t.started_at or datetime.min, reverse=True)


# ─── SSE subscriber broadcast ─────────────────────────────────────────────────

_sse_subscribers: set[asyncio.Queue] = set()


def register_sse_subscriber() -> asyncio.Queue:
    """Register a new SSE subscriber and return its queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _sse_subscribers.add(q)
    return q


def unregister_sse_subscriber(q: asyncio.Queue) -> None:
    """Remove a subscriber queue."""
    _sse_subscribers.discard(q)


def _task_to_sse_dict(task: SubAgentTask) -> dict:
    return {
        "task_id": task.task_id,
        "parent_chat_id": task.parent_chat_id,
        "chat_id": task.chat_id,
        "description": task.description,
        "tools_allowed": task.tools_allowed,
        "status": task.status,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "result_summary": task.result_summary,
        "error": task.error,
    }


def _broadcast_task_update(task: SubAgentTask) -> None:
    """Push a task-state event to all active SSE subscribers (non-blocking)."""
    payload = json.dumps({"event": "task_update", "task": _task_to_sse_dict(task)})
    dead: set[asyncio.Queue] = set()
    for q in _sse_subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.add(q)
    _sse_subscribers.difference_update(dead)


# ─── Tool name resolution ─────────────────────────────────────────────────────


def _resolve_tool_names(tools_allowed: list[str]) -> tuple[list[str], list[str]]:
    """
    Accept both registry class-name keys (e.g. "BashTool") and pydantic-ai
    tool_name aliases (e.g. "bash_execute"). Returns (resolved, unrecognized).
    """
    from suzent.tools.registry import _all_tool_classes

    # Build dual-lookup: class name → class name, tool_name → class name
    lookup: dict[str, str] = {}
    for cls in _all_tool_classes():
        lookup[cls.name] = cls.name
        if cls.tool_name:
            lookup[cls.tool_name] = cls.name

    resolved = []
    unrecognized = []
    for name in tools_allowed:
        canonical = lookup.get(name)
        if canonical:
            if canonical not in resolved:
                resolved.append(canonical)
        else:
            unrecognized.append(name)
    return resolved, unrecognized


# ─── Public spawn API ─────────────────────────────────────────────────────────


async def spawn_subagent(
    parent_chat_id: str,
    description: str,
    tools_allowed: list[str],
    model_override: Optional[str] = None,
    run_in_background: bool = True,
    cwd: Optional[str] = None,
) -> SubAgentTask:
    """
    Create a SubAgentTask and launch it.

    If run_in_background=True (default): fires as asyncio.create_task and returns
    immediately with status=queued (parent chat continues streaming).

    If run_in_background=False: awaits completion before returning; the returned
    task has status=completed/failed with result_summary populated, letting the
    parent tool call return the actual result inline.
    """
    resolved, unrecognized = _resolve_tool_names(tools_allowed)
    if unrecognized:
        logger.warning(
            f"spawn_subagent: unrecognized tool names {unrecognized} — "
            f"use class-name keys (e.g. 'BashTool'). Resolved: {resolved}"
        )

    task_id = f"sub_{uuid.uuid4().hex[:8]}"
    chat_id = f"subagent-{task_id}"

    task = SubAgentTask(
        task_id=task_id,
        parent_chat_id=parent_chat_id,
        description=description,
        tools_allowed=resolved,  # always store resolved canonical names
        chat_id=chat_id,
        cwd=cwd,
    )

    async with _tasks_lock:
        _tasks[task_id] = task
    _broadcast_task_update(task)

    if run_in_background:
        # Fire-and-forget — parent chat keeps streaming
        asyncio.create_task(
            _run_subagent(task, model_override=model_override, wakeup_parent=True),
            name=f"subagent_{task_id}",
        )
    else:
        # Blocking — parent awaits the child's completion
        await _run_subagent(task, model_override=model_override, wakeup_parent=False)

    return task


# ─── Execution ───────────────────────────────────────────────────────────────


async def _run_subagent(
    task: SubAgentTask,
    model_override: Optional[str] = None,
    wakeup_parent: bool = True,
):
    """Execute the sub-agent in an isolated chat, then notify the parent."""
    task.status = "running"
    task.started_at = datetime.now()
    _broadcast_task_update(task)

    db = get_database()

    # Ensure isolated chat record exists
    if not db.get_chat(task.chat_id):
        db.create_chat(
            title=f"Sub-agent: {task.description[:60]}",
            config={
                "platform": "subagent",
                "parent_chat_id": task.parent_chat_id,
                "subagent_task_id": task.task_id,
                "auto_approve_tools": True,
            },
            chat_id=task.chat_id,
        )

    # Emit spawned event to parent chat
    await _notify_parent(
        task,
        "subagent_spawned",
        {
            "task_id": task.task_id,
            "parent_chat_id": task.parent_chat_id,
            "chat_id": task.chat_id,
            "description": task.description,
            "tools_allowed": task.tools_allowed,
        },
    )

    stream_queue = register_background_stream(task.chat_id)
    try:
        from suzent.core.chat_processor import ChatProcessor
        from suzent.agent_manager import build_agent_config

        processor = ChatProcessor()

        # Build config: only pass whitelisted tools
        base_config: dict = {
            "auto_approve_tools": True,
            "memory_enabled": False,
            "platform": "subagent",
        }
        if model_override:
            base_config["model"] = model_override
        if task.tools_allowed:
            base_config["tools"] = list(task.tools_allowed)
        if task.cwd:
            base_config["cwd"] = task.cwd

        config_override = build_agent_config(base_config, require_social_tool=False)

        result_text = await processor.process_turn_text(
            chat_id=task.chat_id,
            user_id=CONFIG.user_id,
            message_content=task.description,
            config_override=config_override,
            _stream_queue=stream_queue,
        )

        task.status = "completed"
        task.result_summary = result_text[:1000] if result_text else "(no output)"
        task.finished_at = datetime.now()
        _broadcast_task_update(task)

        await _notify_parent(
            task,
            "subagent_completed",
            {
                "task_id": task.task_id,
                "result_summary": task.result_summary,
            },
        )

        if wakeup_parent:
            await _wakeup_parent(task)

    except Exception as e:
        logger.error(f"Sub-agent {task.task_id} failed: {e}")
        task.status = "failed"
        task.error = str(e)
        task.finished_at = datetime.now()
        _broadcast_task_update(task)

        await _notify_parent(
            task,
            "subagent_failed",
            {
                "task_id": task.task_id,
                "error": str(e),
            },
        )
    finally:
        unregister_background_stream(task.chat_id)


async def _wakeup_parent(task: SubAgentTask) -> None:
    """
    Trigger a new LLM turn in the parent chat so the parent agent automatically
    processes the sub-agent's completion result without waiting for the user to type.

    Uses is_heartbeat=True so _persist_state skips rebuilding chat.messages from
    the pydantic-ai history. This prevents the [System] trigger message from
    appearing as a user bubble. After post-processing finishes we manually append
    only the assistant response to the display log.

    Skipped if the parent chat is currently streaming (user is mid-conversation).
    """
    if get_active_stream_queue(task.parent_chat_id) is not None:
        logger.debug(
            f"Parent {task.parent_chat_id} is active; skipping wakeup for {task.task_id}"
        )
        return

    try:
        from suzent.core.chat_processor import ChatProcessor
        from suzent.agent_manager import build_agent_config
        from suzent.core.task_registry import wait_for_background_task_prefix

        wake_msg = (
            f"[System] Sub-agent `{task.task_id}` has finished.\n"
            f"Task: {task.description[:300]}\n\n"
            f"Result:\n{task.result_summary}"
        )

        config_override = build_agent_config(
            {"platform": "subagent_wakeup", "memory_enabled": False},
            require_social_tool=False,
        )

        # is_heartbeat=True → _persist_state(skip_messages=True) → only agent_state
        # is saved; chat.messages is left untouched by the rebuild step.
        result_text = await ChatProcessor().process_background_turn(
            chat_id=task.parent_chat_id,
            user_id=CONFIG.user_id,
            message_content=wake_msg,
            config_override=config_override,
            is_heartbeat=True,
        )

        # Wait for the background post-processing task (agent_state save) to finish
        # before we read and write chat.messages, to avoid a race condition.
        try:
            await wait_for_background_task_prefix(
                f"post_process_{task.parent_chat_id}_", timeout=10.0
            )
        except Exception:
            pass

        # Append only the LLM response to the display log.
        # The [System] trigger message is intentionally hidden — it's an internal
        # implementation detail, not something the user typed.
        if result_text:
            db = get_database()
            parent = db.get_chat(task.parent_chat_id)
            if parent is not None:
                messages = list(parent.messages or [])
                messages.append({"role": "assistant", "content": result_text})
                db.update_chat(task.parent_chat_id, messages=messages)

        logger.debug(f"Wakeup turn completed for parent {task.parent_chat_id}")
    except Exception as e:
        logger.warning(f"Failed to wakeup parent {task.parent_chat_id}: {e}")


async def _notify_parent(task: SubAgentTask, event_name: str, data: dict):
    """
    Push a custom SSE event to the parent chat's active stream queue if it
    has one (normal /chat stream), falling back to background_queues (for
    background tryConnect streams, e.g. social/heartbeat chats).
    """
    try:
        from suzent.streaming import _encode_custom

        chunk = _encode_custom(event_name, data)
        # Prefer the active /chat stream queue (normal user interaction)
        q = get_active_stream_queue(task.parent_chat_id)
        if q is None:
            # Fall back to background queue (social/cron background streams)
            q = background_queues.get(task.parent_chat_id)
        if q is not None:
            try:
                q.put_nowait(("chunk", chunk))
            except asyncio.QueueFull:
                pass
    except Exception as e:
        logger.debug(f"Could not push {event_name} to parent queue: {e}")


async def stop_subagent(task_id: str) -> bool:
    """Request cancellation of a running sub-agent."""
    from suzent.core.stream_registry import stop_stream

    task = _tasks.get(task_id)
    if not task:
        return False
    stop_stream(task.chat_id, reason=f"Sub-agent {task_id} stopped by user")
    return True
