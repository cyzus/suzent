"""
Sub-agent runner: spawns isolated background agent tasks with tool whitelisting
and parent-session notification on completion.

Architecture mirrors SchedulerBrain._execute_job but is triggered by the agent
at runtime (via spawn_subagent tool) rather than a cron schedule.
"""

import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.core.stream_registry import (
    register_background_stream,
    unregister_background_stream,
    background_queues,
    get_active_stream_queue,
    stream_controls,
)

logger = get_logger(__name__)

# Tools that sub-agents can never have, regardless of what the caller requests.
# Prevents recursive sub-agent spawning.
_ALWAYS_DENIED: frozenset[str] = frozenset({"SpawnSubagentTool"})

# ─── Wakeup batching ──────────────────────────────────────────────────────────
# When multiple sub-agents finish around the same time, we batch their results
# into a single parent wakeup turn instead of firing one turn per completion.
# Each entry is a completed SubAgentTask waiting to be delivered.

_WAKEUP_BATCH_DELAY = 0.3  # seconds to wait for sibling completions to accumulate

# parent_chat_id → list of finished tasks pending delivery
_pending_wakeups: Dict[str, List["SubAgentTask"]] = {}
# parent_chat_id → debounce asyncio.Task
_wakeup_debounce_tasks: Dict[str, asyncio.Task] = {}
_wakeup_lock = asyncio.Lock()


async def _schedule_wakeup(task: "SubAgentTask") -> None:
    """
    Add a finished task to the pending batch for its parent chat, then start
    (or reset) a debounce timer. When the timer fires, all accumulated tasks
    are delivered in a single LLM turn.
    """
    parent_id = task.parent_chat_id
    async with _wakeup_lock:
        _pending_wakeups.setdefault(parent_id, []).append(task)

        # Cancel existing debounce timer so we wait for more completions
        existing = _wakeup_debounce_tasks.get(parent_id)
        if existing and not existing.done():
            existing.cancel()

        debounce = asyncio.create_task(
            _debounced_wakeup(parent_id),
            name=f"wakeup_debounce_{parent_id}",
        )
        _wakeup_debounce_tasks[parent_id] = debounce


async def _debounced_wakeup(parent_id: str) -> None:
    """Wait briefly, then flush all pending completions as one wakeup turn."""
    try:
        await asyncio.sleep(_WAKEUP_BATCH_DELAY)
    except asyncio.CancelledError:
        return  # A newer completion reset the timer; this task is superseded

    async with _wakeup_lock:
        batch = _pending_wakeups.pop(parent_id, [])
        _wakeup_debounce_tasks.pop(parent_id, None)

    if batch:
        await _wakeup_parent_batch(parent_id, batch)


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
    subagent_type: Optional[str] = None  # profile name, used to select system prompt
    # Phase 2: context forking
    inherit_context: bool = False
    # Phase 3: git worktree isolation
    isolation: str = "none"  # "none" | "worktree"
    isolation_target_path: Optional[str] = None  # caller-supplied git repo root
    worktree_path: Optional[str] = None  # created worktree path (output)
    worktree_branch: Optional[str] = None  # created branch name (output)


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
        "inherit_context": task.inherit_context,
        "isolation": task.isolation,
        "worktree_path": task.worktree_path,
        "worktree_branch": task.worktree_branch,
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
    inherit_context: bool = False,
    isolation: str = "none",
    isolation_target_path: Optional[str] = None,
    subagent_type: Optional[str] = None,
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

    # Strip always-denied tools regardless of how the list was built
    resolved = [t for t in resolved if t not in _ALWAYS_DENIED]

    task_id = f"sub_{uuid.uuid4().hex[:8]}"
    chat_id = f"subagent-{task_id}"

    task = SubAgentTask(
        task_id=task_id,
        parent_chat_id=parent_chat_id,
        description=description,
        tools_allowed=resolved,  # always store resolved canonical names
        chat_id=chat_id,
        cwd=cwd,
        inherit_context=inherit_context,
        isolation=isolation,
        isolation_target_path=isolation_target_path,
        subagent_type=subagent_type,
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

    # Phase 2: inject parent conversation history into child chat
    if task.inherit_context:
        await _fork_context(task, db)

    # Phase 3: create git worktree before streaming starts
    if task.isolation == "worktree":
        error = await _setup_worktree(task)
        if error:
            task.status = "failed"
            task.error = error
            task.finished_at = datetime.now()
            _broadcast_task_update(task)
            await _notify_parent(
                task,
                "subagent_failed",
                {"task_id": task.task_id, "error": error},
            )
            return

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
        from suzent.prompts import SUBAGENT_INSTRUCTIONS

        subagent_prompt = SUBAGENT_INSTRUCTIONS.get(
            task.subagent_type or "", SUBAGENT_INSTRUCTIONS["_default"]
        )

        base_config: dict = {
            "auto_approve_tools": True,
            "memory_enabled": False,
            "platform": "subagent",
            "static_instructions": subagent_prompt,
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
            await _schedule_wakeup(task)

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
        # Phase 3: always tear down the worktree, even on failure
        if task.isolation == "worktree" and task.worktree_path:
            await _teardown_worktree(task)


# ─── Phase 2: Context forking ─────────────────────────────────────────────────


async def _fork_context(task: SubAgentTask, db) -> None:
    """
    Copy the parent chat's serialized message history into the child chat so the
    sub-agent starts with full conversation context. The parent and child diverge
    after this snapshot — neither side sees the other's future messages.
    """
    parent_chat = db.get_chat(task.parent_chat_id)
    if not parent_chat or not parent_chat.agent_state:
        logger.debug(
            f"Context fork skipped for {task.task_id}: parent has no agent_state yet"
        )
        return

    from suzent.core.agent_serializer import deserialize_state, serialize_state

    parent_state = deserialize_state(parent_chat.agent_state)
    if not parent_state or not parent_state.get("message_history"):
        logger.debug(
            f"Context fork skipped for {task.task_id}: parent agent_state has no message_history"
        )
        return

    child_state = serialize_state(
        parent_state["message_history"],
        model_id=parent_state.get("model_id"),
        tool_names=parent_state.get("tool_names", []),
    )
    if child_state:
        db.update_chat(task.chat_id, agent_state=child_state)
        logger.debug(
            f"Forked {len(parent_state['message_history'])} parent messages "
            f"into child chat {task.chat_id}"
        )


# ─── Phase 3: Git worktree lifecycle ─────────────────────────────────────────


async def _setup_worktree(task: SubAgentTask) -> Optional[str]:
    """
    Create a git worktree for the sub-agent. Returns an error string on failure,
    None on success. Mutates task.worktree_path, task.worktree_branch, task.cwd.
    """
    target_path = task.isolation_target_path
    if not target_path:
        return "isolation_target_path is required for worktree isolation"

    # 1. Validate it is a git repo and get the canonical root
    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--show-toplevel",
        cwd=target_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return (
            f"isolation_target_path is not a git repository: {stderr.decode().strip()}"
        )

    git_root = stdout.decode().strip()

    # 2. Verify repo has at least one commit (git worktree add fails on empty repos)
    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "HEAD",
        cwd=git_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode != 0:
        return "Repository has no commits — cannot create worktree"

    # 3. Build slug-safe branch name and worktree path
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", task.task_id)[:64]
    branch_name = f"subagent-{slug}"
    worktree_dir = str(Path(git_root) / ".git" / "worktrees-tmp" / slug)

    # 4. Create worktree on a new branch
    proc = await asyncio.create_subprocess_exec(
        "git",
        "worktree",
        "add",
        "-b",
        branch_name,
        worktree_dir,
        cwd=git_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        return f"git worktree add failed: {stderr.decode().strip()}"

    task.worktree_path = worktree_dir
    task.worktree_branch = branch_name
    task.cwd = worktree_dir  # override any caller-supplied cwd

    logger.info(
        f"Created worktree {worktree_dir} on branch {branch_name} "
        f"for sub-agent {task.task_id}"
    )
    return None


async def _teardown_worktree(task: SubAgentTask) -> None:
    """
    Remove the worktree and delete the branch. Always called in the finally: block
    of _run_subagent. Mirrors test-claude's cleanupWorktree() in utils/worktree.ts:
    - git worktree remove --force with cwd=git_root (never the worktree itself)
    - 100ms sleep for git to release file locks
    - git branch -D to avoid accumulating stale branches
    """
    worktree_path = task.worktree_path
    if not worktree_path:
        return

    # Derive git_root from path convention: <repo>/.git/worktrees-tmp/<slug>
    # MUST NOT use worktree_path as cwd — git rejects removing the current directory.
    git_root = str(Path(worktree_path).parents[2])

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "worktree",
            "remove",
            "--force",
            worktree_path,
            cwd=git_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info(f"Removed worktree {worktree_path}")
    except Exception as e:
        logger.warning(f"Failed to remove worktree {worktree_path}: {e}")

    if task.worktree_branch:
        # Brief pause so git releases file locks before branch deletion
        await asyncio.sleep(0.1)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "branch",
                "-D",
                task.worktree_branch,
                cwd=git_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            logger.info(f"Deleted branch {task.worktree_branch}")
        except Exception as e:
            logger.warning(f"Failed to delete branch {task.worktree_branch}: {e}")


# ─── Parent wakeup & notification ────────────────────────────────────────────


async def _wakeup_parent_batch(parent_chat_id: str, batch: List[SubAgentTask]) -> None:
    """
    Trigger a single LLM turn in the parent chat delivering all finished sub-agents
    at once. Called by _debounced_wakeup after the batch window closes.

    If the parent is currently streaming (user mid-conversation or an earlier wakeup
    turn is still running), wait for the stream to finish before delivering. This
    prevents results from being silently dropped when multiple sub-agents complete
    in quick succession and a wakeup turn is already in flight for an earlier batch.
    """
    control = stream_controls.get(parent_chat_id)
    if control is not None:
        logger.debug(
            f"Parent {parent_chat_id} is streaming; waiting before delivering "
            f"batched wakeup for {[t.task_id for t in batch]}"
        )
        try:
            await asyncio.wait_for(control.completed_event.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            logger.warning(
                f"Timed out waiting for parent {parent_chat_id} stream to finish; "
                f"dropping wakeup for {[t.task_id for t in batch]}"
            )
            return
        logger.debug(f"Parent {parent_chat_id} stream finished; proceeding with wakeup")

    try:
        from suzent.core.chat_processor import ChatProcessor
        from suzent.agent_manager import build_agent_config
        from suzent.core.task_registry import wait_for_background_task_prefix
        from suzent.prompts import (
            SUBAGENT_WAKEUP_SINGLE,
            SUBAGENT_WAKEUP_BATCH_HEADER,
            SUBAGENT_WAKEUP_BATCH_ITEM,
        )

        if len(batch) == 1:
            t = batch[0]
            wake_msg = SUBAGENT_WAKEUP_SINGLE.format(
                task_id=t.task_id,
                description=t.description[:300],
                result_summary=t.result_summary,
            )
        else:
            parts = [SUBAGENT_WAKEUP_BATCH_HEADER.format(count=len(batch))]
            for j, t in enumerate(batch, 1):
                parts.append(
                    SUBAGENT_WAKEUP_BATCH_ITEM.format(
                        index=j,
                        task_id=t.task_id,
                        description=t.description[:200],
                        result_summary=t.result_summary or "(no output)",
                    )
                )
            wake_msg = "\n\n".join(parts)

        logger.debug(
            f"Batched wakeup for {parent_chat_id}: {[t.task_id for t in batch]}"
        )

        config_override = build_agent_config(
            {"platform": "subagent_wakeup", "memory_enabled": False},
            require_social_tool=False,
        )

        # is_heartbeat=True → _persist_state(skip_messages=True) → only agent_state
        # is saved; chat.messages is left untouched by the rebuild step.
        result_text = await ChatProcessor().process_background_turn(
            chat_id=parent_chat_id,
            user_id=CONFIG.user_id,
            message_content="",
            config_override=config_override,
            is_heartbeat=True,
            system_reminders=[wake_msg],
        )

        # Wait for the background post-processing task to finish before writing
        # to chat.messages to avoid a race condition.
        try:
            await wait_for_background_task_prefix(
                f"post_process_{parent_chat_id}_", timeout=10.0
            )
        except Exception:
            pass

        if result_text:
            db = get_database()
            parent = db.get_chat(parent_chat_id)
            if parent is not None:
                messages = list(parent.messages or [])
                messages.append({"role": "assistant", "content": result_text})
                db.update_chat(parent_chat_id, messages=messages)

        logger.debug(f"Batched wakeup turn completed for parent {parent_chat_id}")
    except Exception as e:
        logger.warning(f"Failed batched wakeup for parent {parent_chat_id}: {e}")


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
