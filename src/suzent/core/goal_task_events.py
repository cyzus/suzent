"""Event-bus helpers for goal and task changes."""

from typing import Literal, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

GoalTaskEntity = Literal["goal", "task"]
GoalTaskAction = Literal["created", "updated", "deleted", "cleared"]


def emit_goal_task_changed(
    *,
    entity: GoalTaskEntity,
    action: GoalTaskAction,
    project_id: str,
    chat_id: Optional[str] = None,
    goal_id: Optional[int] = None,
    task_id: Optional[int] = None,
) -> None:
    """Notify UI subscribers that project goal/task data should be refreshed."""
    payload = {
        "event": "goal_tasks_changed",
        "entity": entity,
        "action": action,
        "project_id": project_id,
        "chat_id": chat_id,
        "goal_id": goal_id,
        "task_id": task_id,
    }
    try:
        from suzent.core.stream_registry import emit_bus_event

        emit_bus_event(payload)
    except Exception as exc:
        logger.debug(f"Failed to emit goal/task change event: {exc}")
