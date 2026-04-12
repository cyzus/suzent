"""
Sub-agent management API routes.

GET  /subagents/active           — list currently running sub-agents
GET  /subagents/stream           — SSE stream of task state changes
GET  /subagents                  — list all sub-agents (optionally filter by parent_chat_id)
GET  /subagents/{task_id}        — get a single sub-agent task
POST /subagents/{task_id}/stop   — stop a running sub-agent
"""

import asyncio
import json

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.core.subagent_runner import (
    get_task,
    list_active_tasks,
    list_all_tasks,
    register_sse_subscriber,
    stop_subagent,
    unregister_sse_subscriber,
    _task_to_sse_dict,
)


def _task_to_dict(task) -> dict:
    return {
        "task_id": task.task_id,
        "parent_chat_id": task.parent_chat_id,
        "chat_id": task.chat_id,
        "description": task.description,
        "tools_allowed": task.tools_allowed,
        "status": task.status,
        "result_summary": task.result_summary,
        "error": task.error,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


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
    tasks = list_all_tasks(parent_chat_id=parent_chat_id)
    return JSONResponse({"tasks": [_task_to_dict(t) for t in tasks]})


async def get_subagent(request: Request) -> JSONResponse:
    task_id = request.path_params["task_id"]
    task = get_task(task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return JSONResponse({"task": _task_to_dict(task)})


async def stop_subagent_route(request: Request) -> JSONResponse:
    task_id = request.path_params["task_id"]
    stopped = await stop_subagent(task_id)
    if not stopped:
        return JSONResponse(
            {"error": "Task not found or already finished"}, status_code=404
        )
    return JSONResponse({"ok": True, "task_id": task_id})
