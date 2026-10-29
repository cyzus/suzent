"""Project-related API routes.

Projects group multiple chat sessions and own the shared workspace
(``projects/{slug}/``). Each chat belongs to exactly one project.

Endpoints:
- ``GET    /projects``               list non-archived projects, most recently active first
- ``POST   /projects``               create a new project
- ``PATCH  /projects/{id}``          rename / archive / change settings
- ``DELETE /projects/{id}``          delete an empty, non-system project
- ``POST   /chats/{id}/project``     move a chat to a different project
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.database import get_database
from suzent.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Convert a project name into a URL-safe slug."""
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return slug or "project"


def _normalize_slug(value: object, fallback_name: str) -> str:
    """Normalize a caller-provided slug to the same safe shape as generated slugs."""
    raw = str(value or "").strip()
    return _slugify(raw or fallback_name)


def _project_to_dict(project, chat_count: int) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "slug": project.slug,
        "createdAt": project.created_at.isoformat() if project.created_at else None,
        "archived": project.archived,
        "chatCount": chat_count,
        "workingDirectory": project.working_directory,
    }


def _normalize_working_directory(value: object) -> tuple[str, str | None]:
    """Validate a project working directory from a request body.

    Returns ``(path, error)``. An empty path means "clear the setting".
    """
    if value is None:
        return "", None
    if not isinstance(value, str):
        return "", "'working_directory' must be a string or null"
    raw = value.strip()
    if not raw:
        return "", None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return "", "'working_directory' must be an absolute path"
    path = path.resolve()
    if not path.is_dir():
        return "", f"Folder not found: {path}"
    return str(path), None


def _aware(value: datetime, *, local: bool) -> datetime:
    # SQLite drops tzinfo: chat timestamps are written as local time, project
    # timestamps as UTC, so each needs its own zone back before comparing.
    if value.tzinfo:
        return value
    return value.astimezone() if local else value.replace(tzinfo=timezone.utc)


def _invalidate_sandbox_sessions(chat_ids: list[str]) -> None:
    try:
        from suzent.sandbox import SandboxManager

        for chat_id in chat_ids:
            SandboxManager.invalidate_session(chat_id)
    except Exception as e:
        logger.debug(f"Failed to invalidate sandbox sessions for moved chats: {e}")


def _chat_has_heartbeat_enabled(chat) -> bool:
    return bool(chat and chat.config and chat.config.get("heartbeat_enabled"))


def _any_chat_has_heartbeat_enabled(db, chat_ids: list[str]) -> bool:
    return any(
        _chat_has_heartbeat_enabled(db.get_chat(chat_id)) for chat_id in chat_ids
    )


def _heartbeat_conflict_payload(existing) -> dict:
    return {
        "error": (
            f"Heartbeat is already enabled on chat '{existing.title}' "
            "in the target project. Disable it there first."
        ),
        "conflicting_chat_id": existing.id,
        "conflicting_chat_title": existing.title,
    }


# ---------------------------------------------------------------------------
# /projects
# ---------------------------------------------------------------------------


async def list_projects(request: Request) -> JSONResponse:
    """Return all non-archived projects with chat counts."""
    try:
        db = get_database()
        include_archived = (
            request.query_params.get("include_archived", "").lower() == "true"
        )
        projects = db.list_projects(include_archived=include_archived)
        unread_counts = db.get_project_unread_counts()
        last_activity = db.get_project_last_activity()

        def activity(project) -> datetime:
            if chat_updated := last_activity.get(project.id):
                return _aware(chat_updated, local=True)
            return _aware(project.created_at, local=False)

        projects.sort(key=activity, reverse=True)
        payload = [
            {
                **_project_to_dict(p, db.count_chats_in_project(p.id)),
                "lastActivityAt": activity(p).isoformat(),
                "unreadChatCounts": unread_counts.get(p.id, {}),
            }
            for p in projects
        ]
        return JSONResponse(payload)
    except Exception as e:
        logger.error(f"list_projects failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def create_project(request: Request) -> JSONResponse:
    """Create a new project. Body: ``{name, slug?}``."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "'name' is required"}, status_code=400)

    slug = _normalize_slug(body.get("slug"), name)

    db = get_database()
    if db.get_project_by_slug(slug):
        return JSONResponse(
            {"error": f"A project with slug '{slug}' already exists"},
            status_code=409,
        )
    try:
        project_id = db.create_project(name=name, slug=slug)
    except Exception as e:
        logger.error(f"create_project failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

    project = db.get_project(project_id)
    return JSONResponse(_project_to_dict(project, 0), status_code=201)


async def update_project(request: Request) -> JSONResponse:
    """Update a project. Body: ``{name?, archived?, working_directory?}``.

    ``working_directory`` set to ``null`` or ``""`` clears it.
    """
    project_id = request.path_params.get("project_id")
    if not project_id:
        return JSONResponse({"error": "project_id required"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    name = body.get("name")
    archived = body.get("archived")
    has_working_directory = "working_directory" in body
    if name is None and archived is None and not has_working_directory:
        return JSONResponse(
            {
                "error": (
                    "Provide at least one of 'name', 'archived' or 'working_directory'"
                )
            },
            status_code=400,
        )
    if name is not None:
        name = str(name).strip()
        if not name:
            return JSONResponse({"error": "'name' cannot be empty"}, status_code=400)
    working_directory = None
    if has_working_directory:
        working_directory, error = _normalize_working_directory(
            body.get("working_directory")
        )
        if error:
            return JSONResponse({"error": error}, status_code=400)

    db = get_database()
    project = db.update_project(
        project_id=project_id,
        name=name,
        archived=bool(archived) if archived is not None else None,
        working_directory=working_directory,
    )
    if not project:
        return JSONResponse({"error": "Project not found"}, status_code=404)

    return JSONResponse(
        _project_to_dict(project, db.count_chats_in_project(project_id))
    )


async def delete_project(request: Request) -> JSONResponse:
    """Delete an empty, non-system project."""
    project_id = request.path_params.get("project_id")
    if not project_id:
        return JSONResponse({"error": "project_id required"}, status_code=400)

    db = get_database()
    success, err = db.delete_project(project_id)
    if not success:
        status = 404 if err == "Project not found" else 409
        return JSONResponse({"error": err}, status_code=status)
    return JSONResponse({"success": True})


async def move_all_chats(request: Request) -> JSONResponse:
    """Reassign every chat in a project to another project.

    Body: ``{target_project_id}``. Used by the frontend before deleting a
    non-empty project so its chats land somewhere instead of vanishing.
    """
    project_id = request.path_params.get("project_id")
    if not project_id:
        return JSONResponse({"error": "project_id required"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    target = body.get("target_project_id") or body.get("targetProjectId")
    if not target:
        return JSONResponse(
            {"error": "'target_project_id' is required"}, status_code=400
        )
    if target == project_id:
        return JSONResponse(
            {"error": "target_project_id must differ from source"}, status_code=400
        )

    db = get_database()
    if not db.get_project(project_id):
        return JSONResponse({"error": "Source project not found"}, status_code=404)
    target_project = db.get_project(target)
    if not target_project:
        return JSONResponse({"error": "Target project not found"}, status_code=404)

    source_heartbeat = db.find_heartbeat_enabled_chat_in_project(project_id)
    target_heartbeat = db.find_heartbeat_enabled_chat_in_project(target)
    if source_heartbeat is not None and target_heartbeat is not None:
        return JSONResponse(
            _heartbeat_conflict_payload(target_heartbeat),
            status_code=409,
        )

    moved_chat_ids = db.get_chat_ids_in_project(project_id)
    moved = db.move_all_chats(project_id, target)
    _invalidate_sandbox_sessions(moved_chat_ids)
    return JSONResponse(
        {
            "success": True,
            "moved": moved,
            "targetProjectId": target,
            "targetProjectName": target_project.name,
        }
    )


# ---------------------------------------------------------------------------
# Move chat between projects
# ---------------------------------------------------------------------------


async def move_chat_to_project(request: Request) -> JSONResponse:
    """Move a chat to a different project. Body: ``{project_id}``."""
    chat_id = request.path_params.get("chat_id")
    if not chat_id:
        return JSONResponse({"error": "chat_id required"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    project_id = body.get("project_id")
    if not project_id:
        return JSONResponse({"error": "'project_id' is required"}, status_code=400)

    db = get_database()
    target = db.get_project(project_id)
    if not target:
        return JSONResponse({"error": "Target project not found"}, status_code=404)

    chat = db.get_chat(chat_id)
    if not chat:
        return JSONResponse({"error": "Chat not found"}, status_code=404)

    moved_chat_ids = [chat_id, *db.get_subagent_chat_ids_for_parent_chat(chat_id)]

    if _any_chat_has_heartbeat_enabled(db, moved_chat_ids):
        existing = db.find_heartbeat_enabled_chat_in_project(
            project_id, exclude_chat_ids=set(moved_chat_ids)
        )
        if existing is not None:
            return JSONResponse(
                _heartbeat_conflict_payload(existing),
                status_code=409,
            )

    if not db.link_chat_to_project(chat_id, project_id):
        return JSONResponse({"error": "Chat not found"}, status_code=404)

    _invalidate_sandbox_sessions(moved_chat_ids)

    return JSONResponse(
        {
            "success": True,
            "chatId": chat_id,
            "projectId": project_id,
            "projectSlug": target.slug,
            "projectName": target.name,
        }
    )
