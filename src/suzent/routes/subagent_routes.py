"""
Sub-agent management API routes.

GET  /subagents/active           — list currently running sub-agents
GET  /subagents                  — list all sub-agents (optionally filter by parent_chat_id)
GET  /subagents/{task_id}        — get a single sub-agent task
POST /subagents/{task_id}/stop   — stop a running sub-agent
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.subagent_runner import (
    get_task,
    list_active_tasks,
    list_all_tasks,
    stop_subagent,
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
