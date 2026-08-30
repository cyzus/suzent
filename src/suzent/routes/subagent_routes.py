"""
Sub-agent management API routes.

GET  /subagents/active           — list currently running sub-agents
GET  /subagents/stream           — SSE stream of task state changes
GET  /subagents                  — list bounded recent sub-agents (optionally by parent_chat_id)
GET  /subagents/{task_id}        — get a single sub-agent task
POST /subagents/{task_id}/stop   — stop a running sub-agent
POST /subagents/{task_id}/steer  — redirect a running sub-agent in place
"""

import asyncio
import json

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.core.subagent_runner import (
    SubAgentTask,
    get_task,
    list_active_tasks,
    list_all_tasks,
    register_sse_subscriber,
    stop_subagent,
    steer_subagent,
    unregister_sse_subscriber,
    clear_stuck_tasks,
    _task_to_sse_dict,
)
from suzent.database import get_database

_DEFAULT_LIST_LIMIT = 100
_MAX_LIST_LIMIT = 200


def _task_to_dict(task: SubAgentTask) -> dict:
    return {
        "task_id": task.task_id,
        "parent_chat_id": task.parent_chat_id,
        "chat_id": task.chat_id,
        "description": task.description,
        "tools_allowed": task.tools_allowed,
        "status": task.status,
        "result_summary": task.result_summary,
        "error": task.error,
        "model_override": task.model_override,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def _parse_list_limit(request: Request) -> int:
    raw_limit = request.query_params.get("limit")
    if raw_limit is None:
        return _DEFAULT_LIST_LIMIT
    try:
        limit = int(raw_limit)
    except ValueError:
        return _DEFAULT_LIST_LIMIT
    return min(max(limit, 1), _MAX_LIST_LIMIT)


def _task_sort_key(task: dict) -> tuple[bool, str]:
    return (
        task.get("status") in {"queued", "running"},
        task.get("finished_at") or task.get("started_at") or "",
    )


async def list_active_subagents(request: Request) -> JSONResponse:
    tasks = list_active_tasks()
    return JSONResponse({"tasks": [_task_to_dict(t) for t in tasks]})


async def stream_subagents(request: Request) -> StreamingResponse:
    """SSE endpoint — pushes task_update events as sub-agent state changes."""

    async def event_generator():
        q = register_sse_subscriber()
        try:
            # Send current active-task snapshot on connect so the client is in sync.
            snapshot = [_task_to_sse_dict(t) for t in list_active_tasks()]
            yield f"data: {json.dumps({'event': 'snapshot', 'tasks': snapshot})}\n\n"

            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister_sse_subscriber(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def list_subagents(request: Request) -> JSONResponse:
    parent_chat_id = request.query_params.get("parent_chat_id")
    limit = _parse_list_limit(request)
    runtime_tasks = [
        _task_to_dict(t) for t in list_all_tasks(parent_chat_id=parent_chat_id)
    ]
    persisted_tasks = get_database().list_subagent_task_records(
        parent_chat_id=parent_chat_id, limit=limit + 1
    )

    tasks_by_id = {}
    for task in persisted_tasks:
        task_id = task.get("task_id")
        if task_id:
            tasks_by_id[task_id] = task
    for task in runtime_tasks:
        tasks_by_id[task["task_id"]] = task

    tasks = sorted(tasks_by_id.values(), key=_task_sort_key, reverse=True)
    has_more = len(tasks) > limit or len(persisted_tasks) > limit
    tasks = tasks[:limit]

    return JSONResponse({"tasks": tasks, "has_more": has_more, "limit": limit})


async def get_subagent(request: Request) -> JSONResponse:
    task_id = request.path_params["task_id"]
    task = get_task(task_id)
    if task:
        return JSONResponse({"task": _task_to_dict(task)})

    persisted = get_database().list_subagent_task_records(task_id=task_id, limit=1)
    if persisted:
        return JSONResponse({"task": persisted[0]})

    return JSONResponse({"error": "Task not found"}, status_code=404)


async def stop_subagent_route(request: Request) -> JSONResponse:
    task_id = request.path_params["task_id"]
    stopped = await stop_subagent(task_id)
    if not stopped:
        return JSONResponse(
            {"error": "Task not found or already finished"}, status_code=404
        )
    return JSONResponse({"ok": True, "task_id": task_id})


async def steer_subagent_route(request: Request) -> JSONResponse:
    """Redirect one running sub-agent, leaving its parent's turn untouched."""
    task_id = request.path_params["task_id"]
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON."}, status_code=400)

    message = str(data.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    delivered = await steer_subagent(task_id, message)
    if not delivered:
        return JSONResponse(
            {
                "error": (
                    "Sub-agent is not running, or its turn is not currently "
                    "accepting messages."
                )
            },
            status_code=409,
        )
    return JSONResponse({"ok": True, "task_id": task_id})


async def clear_stuck_subagents_route(request: Request) -> JSONResponse:
    cleared = await clear_stuck_tasks()
    return JSONResponse({"ok": True, "cleared": cleared})
