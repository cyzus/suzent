"""The phone's view of a conversation's side panel: plan, sub-agents, memory and files."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from suzent.core.focal_agent import FOCAL_CHAT_ID
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.mobile.client_api import authorize, forwarded, parse
from suzent.mobile.pairing import ClientGrant
from suzent.routes.mobile_routes import reply

logger = get_logger(__name__)

MAX_FILE_ENTRIES = 500
MAX_TASKS = 50
MAX_AGENTS = 20
MAX_SAVED_FACTS = 20
PUBLIC_PERMISSION_MODES = ("default", "auto", "full_access")


class PermissionModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str = Field(min_length=1, max_length=200, pattern=r"^[^/]+$")
    mode: Literal["default", "auto", "full_access"]


def workspace_allowed(grant: ClientGrant) -> bool:
    # A project's workspace and the memories a turn recalls are shared beyond one
    # chat, so only a phone that may read every conversation sees them.
    return grant.permissions.all_chats


def permission_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("permission_mode") or "default")
    return mode if mode in PUBLIC_PERMISSION_MODES else "default"


def context_usage(config: dict[str, Any], stored: dict[str, Any]) -> dict | None:
    tokens = stored.get("context_tokens")
    if not isinstance(tokens, int) or tokens < 0:
        return None
    from suzent.core.context_compressor import resolve_context_limit
    from suzent.core.providers import get_default_chat_model

    try:
        limit = resolve_context_limit(config.get("model") or get_default_chat_model())
    except Exception:
        logger.debug("No context limit for this chat's model")
        return None
    return {"tokens": tokens, "limit": limit} if limit else None


def plan(chat_id: str, project_id: str | None) -> dict[str, Any]:
    if not project_id:
        return {"goal": None, "tasks": []}
    db = get_database()
    goal = db.get_goal(project_id, chat_id=chat_id)
    tasks = db.list_tasks(
        project_id=project_id,
        chat_id=chat_id,
        include_completed=True,
        include_cancelled=False,
    )
    return {
        "goal": {
            "objective": goal.objective,
            "status": goal.status,
            "turnsElapsed": goal.turns_elapsed,
            "maxTurns": goal.max_turns,
        }
        if goal
        else None,
        "tasks": [
            {
                "id": str(task.id),
                "title": task.title,
                "status": "blocked"
                if task.blocked_by and task.status == "pending"
                else task.status,
                "activeForm": task.active_form,
            }
            # Unfinished work first, so a long history cannot push it past the limit.
            for task in sorted(tasks, key=lambda task: task.status == "completed")[
                :MAX_TASKS
            ]
        ],
    }


def sub_agents(grant: ClientGrant, chat_id: str) -> list[dict[str, Any]]:
    from suzent.core.subagent_runner import list_all_tasks

    by_id: dict[str, dict[str, Any]] = {
        record["task_id"]: record
        for record in get_database().list_subagent_task_records(
            parent_chat_id=chat_id, limit=MAX_AGENTS
        )
        if record.get("task_id")
    }
    for task in list_all_tasks(parent_chat_id=chat_id):
        by_id[task.task_id] = {
            "task_id": task.task_id,
            "chat_id": task.chat_id,
            "description": task.description,
            "status": task.status,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }
    agents = sorted(
        by_id.values(),
        key=lambda task: (
            task.get("status") in {"queued", "running"},
            task.get("finished_at") or task.get("started_at") or "",
        ),
        reverse=True,
    )
    return [
        {
            "id": task["task_id"],
            "description": task.get("description") or "",
            "status": task.get("status") or "unknown",
            # The phone may open a sub-agent's chat only when it may read that chat.
            "chatId": child
            if (child := task.get("chat_id")) and grant.permissions.permits_chat(child)
            else None,
            "startedAt": task.get("started_at"),
            "finishedAt": task.get("finished_at"),
        }
        for task in agents[:MAX_AGENTS]
    ]


async def memory(chat_id: str, created_at: Any) -> dict[str, Any]:
    from suzent.memory.lifecycle import get_memory_manager

    db = get_database()
    recall = await run_in_threadpool(db.get_memory_recall, chat_id)
    saved: list[dict[str, Any]] = []
    manager = get_memory_manager()
    if manager and manager.markdown_store and created_at is not None:
        saved = await run_in_threadpool(
            manager.markdown_store.find_chat_facts,
            chat_id,
            created_at.strftime("%Y-%m-%d"),
            MAX_SAVED_FACTS,
        )
    return {
        "recalled": [
            {"content": item.get("content", ""), "category": item.get("category")}
            for item in (recall.items if recall else [])
        ],
        "saved": [
            {"content": fact["content"], "category": fact.get("category")}
            for fact in saved
        ],
    }


async def details(request: Request) -> JSONResponse:
    chat_id = request.path_params["chat_id"]
    grant = authorize(request, chat_id)
    db = get_database()
    stored = db.get_chat(chat_id)
    if stored is None:
        raise HTTPException(404, "Conversation unavailable")
    config = stored.config or {}
    regent = chat_id == FOCAL_CHAT_ID
    project_id = (
        None if regent else db.get_chat_projects([chat_id]).get(chat_id, (None,))[0]
    )
    shared = workspace_allowed(grant)
    try:
        chat_plan = plan(chat_id, project_id)
    except Exception:
        logger.warning("Could not read the plan for a mobile chat panel")
        chat_plan = {"goal": None, "tasks": []}
    try:
        agents = sub_agents(grant, chat_id)
    except Exception:
        logger.warning("Could not list sub-agents for a mobile chat panel")
        agents = []
    chat_memory = None
    if shared:
        try:
            chat_memory = await memory(chat_id, getattr(stored, "created_at", None))
        except Exception:
            logger.warning("Could not read memory activity for a mobile chat panel")
    return reply(
        {
            "permissionMode": {
                "mode": permission_mode(config),
                "available": list(PUBLIC_PERMISSION_MODES),
                "canChange": grant.permissions.approve_tools and not regent,
            },
            "context": context_usage(
                config, dict(getattr(stored, "context_usage", None) or {})
            ),
            **chat_plan,
            "agents": agents,
            "memory": chat_memory,
            "files": shared and not regent,
        }
    )


def workspace_path(chat_id: str, relative: str) -> tuple[Path, Path]:
    root = get_database().get_project_dir(chat_id).resolve()
    parts = [part for part in relative.replace("\\", "/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise HTTPException(400, "Invalid path")
    target = root.joinpath(*parts).resolve()
    # Resolving first means a symlink cannot lead the phone out of the workspace.
    if target != root and root not in target.parents:
        raise HTTPException(403, "Path outside the workspace")
    return root, target


def authorize_files(request: Request) -> tuple[str, str]:
    chat_id = request.path_params["chat_id"]
    grant = authorize(request, chat_id)
    if not workspace_allowed(grant) or chat_id == FOCAL_CHAT_ID:
        raise HTTPException(403, "Files are not shared with this device")
    path = request.query_params.get("path", "")
    if len(path) > 1000:
        raise HTTPException(400, "Invalid path")
    return chat_id, path


async def files(request: Request) -> JSONResponse:
    chat_id, path = authorize_files(request)
    root, target = workspace_path(chat_id, path)
    if not target.exists():
        if target == root:
            return reply({"path": "", "entries": [], "truncated": False})
        raise HTTPException(404, "Folder not found")
    if not target.is_dir():
        raise HTTPException(400, "Not a folder")

    def listing() -> list[dict[str, Any]]:
        entries = []
        for entry in target.iterdir():
            try:
                stat = entry.stat()
            except OSError:
                continue
            is_dir = entry.is_dir()
            entries.append(
                {
                    "name": entry.name,
                    "isDir": is_dir,
                    "size": 0 if is_dir else stat.st_size,
                    "modifiedAt": stat.st_mtime,
                }
            )
        entries.sort(key=lambda item: (not item["isDir"], item["name"].lower()))
        return entries

    entries = await run_in_threadpool(listing)
    return reply(
        {
            "path": target.relative_to(root).as_posix() if target != root else "",
            "entries": entries[:MAX_FILE_ENTRIES],
            "truncated": len(entries) > MAX_FILE_ENTRIES,
        }
    )


async def file(request: Request) -> FileResponse:
    chat_id, path = authorize_files(request)
    _, target = workspace_path(chat_id, path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(
        target,
        media_type=media_type,
        filename=target.name,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def set_permission_mode(request: Request) -> JSONResponse:
    # Choosing auto or full access approves tool calls in advance, so it needs the
    # same grant as answering an approval.
    body = await parse(request, PermissionModeRequest)
    authorize(request, body.chat_id, action="approve_tools")
    if body.chat_id == FOCAL_CHAT_ID:
        raise HTTPException(403, "Regent's mode is set on the desktop")
    from suzent.routes.chat_routes import set_permission_mode as desktop_set_mode

    inner = forwarded(request, {"mode": body.mode})
    inner.scope["path_params"] = {"chat_id": body.chat_id}
    response = await desktop_set_mode(inner)
    if response.status_code != 200:
        return response
    return reply({"mode": json.loads(response.body)["mode"]})


chat_detail_routes = [
    Route("/mobile/client/chats/{chat_id}/details", details, methods=["GET"]),
    Route("/mobile/client/chats/{chat_id}/files", files, methods=["GET"]),
    Route("/mobile/client/chats/{chat_id}/file", file, methods=["GET"]),
    Route("/mobile/client/permission-mode", set_permission_mode, methods=["POST"]),
]
