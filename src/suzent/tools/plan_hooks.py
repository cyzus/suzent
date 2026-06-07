from typing import Any, Optional

from suzent.database import get_database
from suzent.logger import get_logger

logger = get_logger(__name__)


async def plan_reminder_hook(chat_id: str, deps: Any) -> Optional[str]:
    """Inject the active project Goal and open Tasks into the system reminder each turn."""
    db = get_database()
    project_id = db.get_chat_project_id(chat_id)
    if not project_id:
        return None

    parts = []

    goal = db.get_goal(project_id, chat_id=chat_id)
    if goal and goal.status == "active":
        turns_info = ""
        over_budget = False
        if goal.max_turns:
            remaining = goal.max_turns - goal.turns_elapsed
            turns_info = f" ({goal.turns_elapsed}/{goal.max_turns} turns used, {remaining} remaining)"
            over_budget = remaining <= 0
        parts.append(f"[ACTIVE GOAL] {goal.objective}{turns_info}")
        for sg in goal.subgoals:
            parts.append(f"  - {sg}")
        if over_budget:
            parts.append(
                "**WARNING: turn budget exhausted.** You must stop working on this goal, "
                "call manage_goal(action='pause') immediately, and inform the user."
            )
        else:
            parts.append(
                "Evaluate: if the goal is achieved call manage_goal(action='clear'). Otherwise keep working."
            )
        db.update_goal(goal.id, turns_elapsed=goal.turns_elapsed + 1)

    active_tasks = db.list_tasks(
        project_id=project_id,
        include_completed=False,
        include_cancelled=False,
    )
    if active_tasks:
        parts.append(f"\n[ACTIVE TASKS] (project: {project_id})")
        for task in active_tasks:
            assignee_str = f" ({task.assignee})" if task.assignee else ""
            blocks_str = (
                f" blocks: {', '.join(f'#{b}' for b in task.blocks)}"
                if task.blocks
                else ""
            )
            blocked_by_str = (
                f" blocked by: {', '.join(f'#{b}' for b in task.blocked_by)}"
                if task.blocked_by
                else ""
            )
            parts.append(
                f"  [#{task.id}] {task.title}{assignee_str} — {task.status}{blocks_str}{blocked_by_str}"
            )
            parts.append(f"    {task.description}")

    return "\n".join(parts) if parts else None
