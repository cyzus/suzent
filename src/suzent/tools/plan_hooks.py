import asyncio
from typing import Any, Optional

from suzent.database import get_database
from suzent.logger import get_logger

logger = get_logger(__name__)


def active_goal_identity(chat_id: str) -> Optional[tuple[int, int]]:
    """Identity of the goal active for *chat_id* right now, as (id, generation).

    Read at turn start so the charge can be pinned to it. Without that, a goal
    created during the turn is billed for its own setup, and at max_turns=1 it
    pauses before running a single autonomous step.

    Generation rather than objective text. Replacing a goal reuses the row and
    resets turns_elapsed, so the id is unchanged — and the objective can be
    re-set to the same string, for instance to change only max_turns, so that
    does not distinguish them either. The counter is bumped on replacement and
    nothing else, which is the property actually needed.
    """
    try:
        db = get_database()
        project_id = db.get_chat_project_id(chat_id)
        if not project_id:
            return None
        goal = db.get_goal(project_id, chat_id=chat_id)
        if goal and goal.status == "active":
            return (goal.id, goal.generation or 0)
    except Exception as e:
        logger.debug(f"Could not read active goal for chat {chat_id}: {e}")
    return None


def advance_goal_turn(
    chat_id: str, only_goal: Optional[tuple[int, int]] = None
) -> None:
    """Charge one turn against the active goal's budget.

    Called once per completed user turn from the chat lifecycle, not from the
    reminder hook. Building a prompt is a read, and this used to run inside it —
    so the budget was charged by every path that assembled a reminder, including
    heartbeats, approval resumes and tool continuations, none of which are a turn
    the user took. Retries charged again for work already paid for.

    Best-effort: a goal that misses one increment is better than a turn that
    fails because its bookkeeping did.
    """
    try:
        db = get_database()
        project_id = db.get_chat_project_id(chat_id)
        if not project_id:
            return
        goal = db.get_goal(project_id, chat_id=chat_id)
        if not goal or goal.status != "active":
            return
        # Only the goal that was already running when the turn began. One
        # created — or replaced — during the turn did not cost it anything.
        if only_goal is not None and (goal.id, goal.generation or 0) != only_goal:
            logger.debug(
                f"Not charging chat {chat_id}: the active goal changed during the turn"
            )
            return
        db.update_goal(goal.id, turns_elapsed=goal.turns_elapsed + 1)
    except Exception as e:
        logger.warning(f"Could not advance goal turn count for chat {chat_id}: {e}")


async def plan_reminder_hook(chat_id: str, deps: Any) -> Optional[str]:
    """Inject the active project Goal and open Tasks into the system reminder.

    Pure read, and deliberately so: reminder providers run on every path that
    assembles a prompt, so anything mutating here is charged to turns the user
    never took — see advance_goal_turn.

    The body is synchronous database access, which is why it runs on a worker
    thread. A provider that blocks the event loop cannot be timed out, because
    cancelling needs the loop to run, so a stalled database would otherwise hold
    the turn open past the provider deadline. Being read-only is what makes that
    safe: a thread that outlives its cancelled await changes nothing.
    """
    return await asyncio.to_thread(_build_plan_reminder, chat_id)


def _build_plan_reminder(chat_id: str) -> Optional[str]:
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
