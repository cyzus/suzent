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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from suzent.config import CONFIG
from suzent.database import ChatDatabase, get_database
from suzent.logger import get_logger
from suzent.core.stream_registry import (
    register_background_stream,
    unregister_background_stream,
    background_queues,
    get_active_stream_queue,
)

logger = get_logger(__name__)

# Tools that sub-agents can never have, regardless of what the caller requests.
# Prevents recursive sub-agent spawning.
_ALWAYS_DENIED: frozenset[str] = frozenset(
    {
        "AgentTool",
        "AgentListTool",
        "AgentReadTool",
        "AgentSendTool",
        "AgentStopTool",
    }
)

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
    model_override: Optional[str] = (
        None  # resolved model ID (override or default fallback)
    )
    runtime: str = "native"
    acp_agent_id: Optional[str] = None
    acp_session_id: Optional[str] = None
    # Phase 2: context forking
    inherit_context: bool = False
    # Phase 3: git worktree isolation
    isolation: str = "none"  # "none" | "worktree"
    isolation_target_path: Optional[str] = None  # caller-supplied git repo root
    worktree_path: Optional[str] = None  # created worktree path (output)
    worktree_branch: Optional[str] = None  # created branch name (output)
    runner_task: Optional[asyncio.Task] = field(default=None, repr=False)


# Global registry: task_id -> SubAgentTask
_tasks: Dict[str, SubAgentTask] = {}
_tasks_lock = asyncio.Lock()

# Cap on finished (completed/failed) tasks retained for UI history. Active
# (queued/running) tasks are never evicted. Without this, _tasks grows without
# bound for the process lifetime — one SubAgentTask (with its result/error) per
# spawn, forever — a slow leak on long-running servers.
_MAX_FINISHED_TASKS = 200
_TERMINAL_STATUSES = ("completed", "failed")


def _evict_old_finished_tasks() -> None:
    """Drop the oldest finished tasks beyond _MAX_FINISHED_TASKS.

    Caller must hold _tasks_lock. Active tasks are kept regardless of count.
    """
    finished = [t for t in _tasks.values() if t.status in _TERMINAL_STATUSES]
    if len(finished) <= _MAX_FINISHED_TASKS:
        return
    # Oldest first — evict by finish time (falling back to start time).
    finished.sort(key=lambda t: t.finished_at or t.started_at or datetime.min)
    for task in finished[: len(finished) - _MAX_FINISHED_TASKS]:
        _tasks.pop(task.task_id, None)


async def _evict_old_finished_tasks_locked() -> None:
    """Acquire _tasks_lock and evict old finished tasks.

    Called when a task reaches a terminal state, so a burst of subagents that
    all finish without any new spawn still gets pruned (registration-time
    eviction alone would leave those result summaries resident until the next
    spawn).
    """
    async with _tasks_lock:
        _evict_old_finished_tasks()


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
        "model_override": task.model_override,
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


def _persist_task_state(task: SubAgentTask) -> None:
    """Mirror runtime lifecycle fields into the persisted child chat config."""
    db = get_database()
    chat = db.get_chat(task.chat_id)
    if chat is None:
        return
    config = dict(chat.config or {})
    config.update(
        {
            "subagent_status": task.status,
            "subagent_result_summary": task.result_summary,
            "subagent_error": task.error,
            "subagent_model": task.model_override,
            "runtime": task.runtime,
            "acp_agent_id": task.acp_agent_id,
            "acp_session_id": task.acp_session_id,
            "tools": list(task.tools_allowed),
            "inherit_context": task.inherit_context,
            "isolation": task.isolation,
            "worktree_path": task.worktree_path,
            "worktree_branch": task.worktree_branch,
            "subagent_started_at": task.started_at.isoformat()
            if task.started_at
            else None,
            "subagent_finished_at": task.finished_at.isoformat()
            if task.finished_at
            else None,
        }
    )
    db.update_chat(task.chat_id, config=config)


def _ensure_task_chat(task: SubAgentTask) -> ChatDatabase:
    """Create the persisted child chat before task execution is scheduled."""
    db = get_database()
    if db.get_chat(task.chat_id):
        return db

    parent_project_id = (
        db.get_chat_project_id(task.parent_chat_id) if task.parent_chat_id else None
    )
    db.create_chat(
        title=f"Sub-agent: {task.description[:60]}",
        config={
            "platform": "subagent",
            "parent_chat_id": task.parent_chat_id,
            "subagent_task_id": task.task_id,
            "permission_mode": "auto",
            "interaction_profile": "subagent",
            "subagent_status": task.status,
            "subagent_model": task.model_override,
            "runtime": task.runtime,
            "acp_agent_id": task.acp_agent_id,
            "acp_session_id": task.acp_session_id,
            "tools": list(task.tools_allowed),
            "inherit_context": task.inherit_context,
            "isolation": task.isolation,
        },
        chat_id=task.chat_id,
        project_id=parent_project_id,
    )
    return db


# ─── Tool name resolution ─────────────────────────────────────────────────────


def _resolve_tool_names(tools_allowed: list[str]) -> tuple[list[str], list[str]]:
    """
    Accept both registry class-name keys (e.g. "RunCommandTool") and pydantic-ai
    tool_name aliases (e.g. "run_command"). Returns (resolved, unrecognized).
    """
    from suzent.tools.registry import _all_tool_classes, migrate_shell_tool_names

    # Build dual-lookup: class name → class name, tool_name → class name.
    lookup: dict[str, str] = {}
    for cls in _all_tool_classes():
        lookup[cls.name] = cls.name
        if cls.tool_name:
            lookup[cls.tool_name] = cls.name
    resolved = []
    unrecognized = []
    for name in migrate_shell_tool_names(tools_allowed):
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
    runtime: str = "native",
    acp_agent_id: Optional[str] = None,
    acp_session_id: Optional[str] = None,
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
            f"use class-name keys (e.g. 'RunCommandTool'). Resolved: {resolved}"
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
        model_override=model_override,
        runtime=runtime,
        acp_agent_id=acp_agent_id,
        acp_session_id=acp_session_id,
    )

    async with _tasks_lock:
        _tasks[task_id] = task
        _evict_old_finished_tasks()

    try:
        _ensure_task_chat(task)
        _persist_task_state(task)
    except Exception as exc:
        logger.error(f"Failed to persist sub-agent {task_id}: {exc}")
        task.status = "failed"
        task.error = str(exc)
        task.finished_at = datetime.now()
        _broadcast_task_update(task)
        return task

    _broadcast_task_update(task)

    if run_in_background:
        # Use the shared registry so sub-agents participate in concurrency limits,
        # graceful shutdown, exception collection, and task diagnostics.
        from suzent.core.task_registry import register_background_task

        runner = _run_subagent(task, wakeup_parent=True)
        try:
            task.runner_task = await register_background_task(
                runner,
                task_id=f"subagent_{task_id}",
                description=description[:200],
            )
        except Exception as exc:
            runner.close()
            task.status = "failed"
            task.error = str(exc)
            task.finished_at = datetime.now()
            _broadcast_task_update(task)
            _persist_task_state(task)
    else:
        # Blocking — parent awaits the child's completion
        await _run_subagent(task, wakeup_parent=False)

    return task


# ─── Execution ───────────────────────────────────────────────────────────────


async def _run_subagent(
    task: SubAgentTask,
    wakeup_parent: bool = True,
):
    """Execute the sub-agent in an isolated chat, then notify the parent."""
    try:
        if task.runtime != "acp" and not task.model_override:
            from suzent.core.providers import get_default_chat_model

            task.model_override = get_default_chat_model()

        task.status = "running"
        task.started_at = datetime.now()
        _broadcast_task_update(task)

        # The queued state is persisted before scheduling, so other clients can
        # see the task immediately and cancellation cannot lose its lifecycle record.
        db = _ensure_task_chat(task)
        _persist_task_state(task)

        if task.inherit_context:
            await _fork_context(task, db)

        if task.isolation == "worktree":
            setup_error = await _setup_worktree(task)
            if setup_error:
                raise RuntimeError(setup_error)
    except asyncio.CancelledError:
        task.status = "failed"
        task.error = task.error or "Sub-agent cancelled during setup"
        task.finished_at = datetime.now()
        _broadcast_task_update(task)
        _persist_task_state(task)
        raise
    except Exception as exc:
        logger.error(f"Sub-agent {task.task_id} setup failed: {exc}")
        task.status = "failed"
        task.error = str(exc)
        task.finished_at = datetime.now()
        _broadcast_task_update(task)
        try:
            _persist_task_state(task)
        except Exception as persist_error:
            logger.warning(
                f"Could not persist failed sub-agent {task.task_id}: {persist_error}"
            )
        if task.isolation == "worktree" and task.worktree_path:
            await _teardown_worktree(task)
        await _notify_parent(
            task,
            "subagent_failed",
            {"task_id": task.task_id, "error": str(exc)},
        )
        if wakeup_parent:
            _queue_parent_wakeup(task)
        await _evict_old_finished_tasks_locked()
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
            "model_override": task.model_override,
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

        # Inherit parent chat's custom sandbox volumes so the subagent sees the
        # same custom mounts that were configured for the parent session.
        parent_chat = db.get_chat(task.parent_chat_id)
        parent_sandbox_volumes = (
            (parent_chat.config or {}).get("sandbox_volumes") if parent_chat else None
        )
        parent_permission_mode = (
            (parent_chat.config or {}).get("permission_mode") if parent_chat else None
        )
        subagent_permission_mode = (
            parent_permission_mode
            if parent_permission_mode in {"plan", "strict_readonly"}
            else "auto"
        )

        base_config: dict = {
            "permission_mode": subagent_permission_mode,
            "interaction_profile": "subagent",
            "memory_enabled": False,
            "platform": "subagent",
            "static_instructions": subagent_prompt,
        }
        if parent_sandbox_volumes:
            base_config["sandbox_volumes"] = parent_sandbox_volumes
        if task.model_override:
            base_config["model"] = task.model_override
        if task.tools_allowed:
            base_config["tools"] = list(task.tools_allowed)
        if task.cwd:
            base_config["cwd"] = task.cwd

        if task.runtime == "acp":
            if not task.acp_agent_id:
                raise ValueError("acp_agent_id is required when runtime='acp'")
            base_config.update(
                {
                    "runtime": "acp",
                    "acp_agent_id": task.acp_agent_id,
                    "acp_session_id": task.acp_session_id,
                    "acp_cwd": task.cwd or str(Path.cwd()),
                }
            )
            db.merge_chat_config(task.chat_id, base_config)
            from suzent.acp.runtime import run_acp_turn_text

            result_text = await run_acp_turn_text(
                task.chat_id, task.description, base_config, stream_queue
            )
            refreshed = db.get_chat(task.chat_id)
            task.acp_session_id = (
                (refreshed.config or {}).get("acp_session_id") if refreshed else None
            )
        else:
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
        _persist_task_state(task)

        await _notify_parent(
            task,
            "subagent_completed",
            {
                "task_id": task.task_id,
                "result_summary": task.result_summary,
            },
        )

        if wakeup_parent:
            _queue_parent_wakeup(task)

    except asyncio.CancelledError:
        task.status = "failed"
        task.error = task.error or "Sub-agent cancelled"
        task.finished_at = datetime.now()
        _broadcast_task_update(task)
        _persist_task_state(task)
        raise
    except Exception as e:
        logger.error(f"Sub-agent {task.task_id} failed: {e}")
        task.status = "failed"
        task.error = str(e)
        task.finished_at = datetime.now()
        _broadcast_task_update(task)
        _persist_task_state(task)

        await _notify_parent(
            task,
            "subagent_failed",
            {
                "task_id": task.task_id,
                "error": str(e),
            },
        )
        if wakeup_parent:
            _queue_parent_wakeup(task)
    finally:
        unregister_background_stream(task.chat_id)
        # An ACP sub-agent owns a subprocess; without this it outlives the task
        # and only dies at server shutdown. Close it before the worktree goes
        # away, since the agent's cwd may point inside it.
        if task.runtime == "acp":
            try:
                from suzent.acp import get_acp_manager

                await get_acp_manager().close(task.chat_id)
            except Exception as exc:
                logger.warning(f"Failed to close ACP session for {task.task_id}: {exc}")
        # Phase 3: always tear down the worktree, even on failure
        if task.isolation == "worktree" and task.worktree_path:
            await _teardown_worktree(task)
        _persist_task_state(task)
        # The task is now terminal; prune here too so a burst that all finishes
        # without a new spawn doesn't leave result summaries resident.
        await _evict_old_finished_tasks_locked()


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


def _queue_parent_wakeup(task: SubAgentTask) -> None:
    """Persist a completion or failure message for the parent agent."""
    from suzent.core.agent_inbox import enqueue_agent_message
    from suzent.prompts import SUBAGENT_WAKEUP_SINGLE

    if task.status == "completed":
        content = SUBAGENT_WAKEUP_SINGLE.format(
            task_id=task.task_id,
            model_override=task.model_override or "(default)",
            description=task.description[:300],
            result_summary=task.result_summary or "(no output)",
        )
    else:
        content = (
            f"Sub-agent {task.task_id} failed.\n"
            f"Task: {task.description[:300]}\n"
            f"Error: {task.error or 'unknown error'}"
        )
    try:
        enqueue_agent_message(
            message_id=f"subagent-result-{task.task_id}",
            sender_chat_id=task.chat_id,
            target_chat_id=task.parent_chat_id,
            content=content,
            kind="subagent_result",
            payload={"task_id": task.task_id, "status": task.status},
        )
    except Exception as exc:
        logger.warning(
            f"Could not queue parent wakeup for sub-agent {task.task_id}: {exc}"
        )


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


async def clear_stuck_tasks() -> list[str]:
    """Mark all queued/running tasks as failed and broadcast updates.

    Used to recover from stuck state after a crash or unexpected shutdown.
    Returns list of cleared task_ids.
    """
    cleared = []
    for task in list(_tasks.values()):
        if task.status in ("queued", "running"):
            from suzent.core.stream_registry import stop_stream

            stop_stream(task.chat_id, reason=f"Sub-agent {task.task_id} cleared")
            task.status = "failed"
            task.error = "Cleared (orphaned task)"
            task.finished_at = datetime.now()
            _broadcast_task_update(task)
            _persist_task_state(task)
            if task.runner_task and not task.runner_task.done():
                task.runner_task.cancel()
            cleared.append(task.task_id)
    if cleared:
        await _evict_old_finished_tasks_locked()
    return cleared


async def stop_subagent(task_id: str) -> bool:
    """Request cancellation of a running sub-agent."""
    from suzent.core.stream_registry import stop_stream

    task = _tasks.get(task_id)
    if not task or task.status not in ("queued", "running"):
        return False
    stop_stream(task.chat_id, reason=f"Sub-agent {task_id} stopped by user")
    # Mark failed immediately so the UI clears it even if the coroutine is slow
    # to observe the cancel signal.
    if task.status in ("queued", "running"):
        task.status = "failed"
        task.error = "Stopped by user"
        task.finished_at = datetime.now()
        _broadcast_task_update(task)
        _persist_task_state(task)
        if task.runner_task and not task.runner_task.done():
            task.runner_task.cancel()
    return True
