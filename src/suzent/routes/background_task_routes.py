"""Unified sidebar API for long-running user tasks."""

import asyncio
import json
from collections.abc import AsyncIterator

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.core.background_commands import get_background_commands
from suzent.core.subagent_runner import (
    _task_to_sse_dict,
    list_all_tasks,
    register_sse_subscriber,
    unregister_sse_subscriber,
)
from suzent.routes.subagent_routes import (
    _parse_list_limit,
    _task_sort_key,
    get_subagent,
    list_subagents,
    stop_subagent_route,
)


async def list_background_tasks(request: Request) -> JSONResponse:
    response = await list_subagents(request)
    data = json.loads(response.body)
    tasks = [dict(task, kind="subagent") for task in data["tasks"]]
    tasks.extend(
        get_background_commands().list_tasks(request.query_params.get("parent_chat_id"))
    )
    tasks.sort(key=_task_sort_key, reverse=True)
    limit = _parse_list_limit(request)
    return JSONResponse(
        {"tasks": tasks[:limit], "has_more": data["has_more"] or len(tasks) > limit}
    )


async def get_background_task(request: Request) -> JSONResponse:
    task_id = request.path_params["task_id"]
    if task_id.startswith("shell_"):
        task = get_background_commands().get(task_id)
        return JSONResponse(
            {"task": task} if task else {"error": "Task not found"},
            status_code=200 if task else 404,
        )
    return await get_subagent(request)


async def stop_background_task(request: Request) -> JSONResponse:
    task_id = request.path_params["task_id"]
    if task_id.startswith("shell_"):
        stopped = await get_background_commands().stop_command(task_id)
        return JSONResponse({"ok": stopped}, status_code=200 if stopped else 404)
    return await stop_subagent_route(request)


async def stream_background_tasks(request: Request) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        queue = register_sse_subscriber()
        try:
            commands = get_background_commands().list_tasks()
            known = {task["task_id"]: task for task in commands}
            tasks = [
                dict(_task_to_sse_dict(task), kind="subagent")
                for task in list_all_tasks()
            ]
            yield f"data: {json.dumps({'event': 'snapshot', 'tasks': tasks + commands})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=1)
                    yield f"data: {payload}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
                commands = get_background_commands().list_tasks()
                for task in commands:
                    if known.get(task["task_id"]) != task:
                        yield f"data: {json.dumps({'event': 'task_update', 'task': task})}\n\n"
                known = {task["task_id"]: task for task in commands}
        finally:
            unregister_sse_subscriber(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
