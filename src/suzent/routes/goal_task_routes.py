"""Goal and Task API routes for frontend polling and human-operated board."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.database import get_database


def _goal_to_dict(goal) -> dict:
    return {
        "id": goal.id,
        "projectId": goal.project_id,
        "chatId": goal.chat_id,
        "objective": goal.objective,
        "status": goal.status,
        "subgoals": goal.subgoals or [],
        "maxTurns": goal.max_turns,
        "turnsElapsed": goal.turns_elapsed,
        "createdAt": goal.created_at.isoformat() if goal.created_at else None,
        "updatedAt": goal.updated_at.isoformat() if goal.updated_at else None,
        "completedAt": goal.completed_at.isoformat() if goal.completed_at else None,
    }


def _task_to_dict(task) -> dict:
    # Derive blocked state from blocked_by instead of storing it as explicit status
    blocked_by = task.blocked_by or []
    effective_status = (
        "blocked" if blocked_by and task.status == "pending" else task.status
    )
    return {
        "id": task.id,
        "projectId": task.project_id,
        "chatId": task.chat_id,
        "title": task.title,
        "description": task.description,
        "activeForm": task.active_form,
        "status": effective_status,
        "assignee": task.assignee,
        "blocks": task.blocks or [],
        "blockedBy": task.blocked_by or [],
        "createdAt": task.created_at.isoformat() if task.created_at else None,
        "updatedAt": task.updated_at.isoformat() if task.updated_at else None,
        "completedAt": task.completed_at.isoformat() if task.completed_at else None,
    }


async def get_project_goal(request: Request) -> JSONResponse:
    """Return the active goal for a chat (chat-scoped).

    Query parameters:
    - project_id: The project identifier (required)
    - chat_id: The chat identifier — filters to goals owned by this chat (required)
    """
    try:
        project_id = request.query_params.get("project_id")
        chat_id = request.query_params.get("chat_id")
        if not project_id or not chat_id:
            return JSONResponse(
                {"error": "project_id and chat_id are required"}, status_code=400
            )
        db = get_database()
        goal = db.get_goal(project_id, chat_id=chat_id)
        return JSONResponse(_goal_to_dict(goal) if goal else None)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_project_tasks(request: Request) -> JSONResponse:
    """Return tasks for a chat (chat-scoped).

    Query parameters:
    - project_id: The project identifier (required)
    - chat_id: The chat identifier — filters to tasks owned by this chat (required)
    - include_completed: Include completed tasks (default: false)
    - include_cancelled: Include cancelled tasks (default: false)
    """
    try:
        project_id = request.query_params.get("project_id")
        chat_id = request.query_params.get("chat_id")
        if not project_id or not chat_id:
            return JSONResponse(
                {"error": "project_id and chat_id are required"}, status_code=400
            )
        include_completed = (
            request.query_params.get("include_completed", "false").lower() == "true"
        )
        include_cancelled = (
            request.query_params.get("include_cancelled", "false").lower() == "true"
        )
        db = get_database()
        tasks = db.list_tasks(
            project_id=project_id,
            chat_id=chat_id,
            include_completed=include_completed,
            include_cancelled=include_cancelled,
        )
        return JSONResponse([_task_to_dict(t) for t in tasks])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_project_kanban(request: Request) -> JSONResponse:
    """Return all goals and tasks across the project (for kanban view).

    Query parameters:
    - project_id: The project identifier (required)
    """
    try:
        project_id = request.query_params.get("project_id")
        if not project_id:
            return JSONResponse({"error": "project_id is required"}, status_code=400)
        db = get_database()
        goals = db.list_goals_for_project(project_id)
        tasks = db.list_tasks(
            project_id=project_id,
            include_completed=True,
            include_cancelled=False,
        )
        return JSONResponse(
            {
                "goals": [_goal_to_dict(g) for g in goals],
                "tasks": [_task_to_dict(t) for t in tasks],
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def create_project_task(request: Request) -> JSONResponse:
    """Create a task on a project (human-operated board).

    Body JSON: { project_id, title, description?, status?, chat_id? }
    """
    try:
        body = await request.json()
        project_id = body.get("project_id")
        title = (body.get("title") or "").strip()
        if not project_id or not title:
            return JSONResponse(
                {"error": "project_id and title are required"}, status_code=400
            )
        db = get_database()
        task = db.create_task(
            project_id=project_id,
            title=title,
            description=body.get("description") or "",
            status=body.get("status") or "pending",
            chat_id=body.get("chat_id"),
            assignee=body.get("chat_id") or "human",
        )
        return JSONResponse(_task_to_dict(task), status_code=201)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_project_task(request: Request) -> JSONResponse:
    """Update a task status/title/description (human-operated board).

    Path param: task_id
    Body JSON: any subset of { status, title, description }
    """
    try:
        task_id = int(request.path_params["task_id"])
        body = await request.json()
        db = get_database()
        task = db.get_task(task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)
        updates = {k: body[k] for k in ("status", "title", "description") if k in body}
        if updates:
            task = db.update_task(task_id, **updates)
        return JSONResponse(_task_to_dict(task))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def delete_project_task(request: Request) -> JSONResponse:
    """Delete a task (human-operated board)."""
    try:
        task_id = int(request.path_params["task_id"])
        db = get_database()
        deleted = db.delete_task(task_id)
        if not deleted:
            return JSONResponse({"error": "Task not found"}, status_code=404)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
