"""Project-related API routes.

Projects group multiple chat sessions and own the shared workspace
(``projects/{slug}/``). Each chat belongs to exactly one project.

Endpoints:
- ``GET    /projects``               list all non-archived projects with chat counts
- ``POST   /projects``               create a new project
- ``PATCH  /projects/{id}``          rename / archive
- ``DELETE /projects/{id}``          delete an empty, non-system project
- ``POST   /chats/{id}/project``     move a chat to a different project
"""

import re

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


def _project_to_dict(project, chat_count: int) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "slug": project.slug,
        "createdAt": project.created_at.isoformat() if project.created_at else None,
        "archived": project.archived,
        "chatCount": chat_count,
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
        payload = [
            _project_to_dict(p, db.count_chats_in_project(p.id)) for p in projects
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

    slug = (body.get("slug") or "").strip().lower() or _slugify(name)

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
    """Rename or archive a project. Body: ``{name?, archived?}``."""
    project_id = request.path_params.get("project_id")
    if not project_id:
        return JSONResponse({"error": "project_id required"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    name = body.get("name")
    archived = body.get("archived")
    if name is None and archived is None:
        return JSONResponse(
            {"error": "Provide at least one of 'name' or 'archived'"},
            status_code=400,
        )
    if name is not None:
        name = str(name).strip()
        if not name:
            return JSONResponse({"error": "'name' cannot be empty"}, status_code=400)

    db = get_database()
    project = db.update_project(
        project_id=project_id,
        name=name,
        archived=bool(archived) if archived is not None else None,
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

    if not db.link_chat_to_project(chat_id, project_id):
        return JSONResponse({"error": "Chat not found"}, status_code=404)

    return JSONResponse(
        {
            "success": True,
            "chatId": chat_id,
            "projectId": project_id,
            "projectSlug": target.slug,
            "projectName": target.name,
        }
    )
