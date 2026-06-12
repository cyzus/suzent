"""User-facing goal-mode slash commands: /goal and /subgoal.

Thin wrappers over the canonical GoalModel store (same data the `manage_goal`
tool and the right-sidebar read), plus the judge-driven continuation loop in
``suzent.core.goals``. Gives the user direct stop/start control the agent tool
and read-only sidebar don't provide.
"""

import typer

from suzent.core.commands.base import register_command, CommandContext


def _schedule_step(chat_id: str, user_id: str) -> None:
    """Kick off the first/next autonomous goal turn (deferred until the
    command-response stream finishes — see suzent.core.goals)."""
    from suzent.core.goals import schedule_goal_step

    schedule_goal_step(chat_id, user_id)


def _resolve_project_id(chat_id: str):
    from suzent.database import get_database

    return get_database().get_chat_project_id(chat_id)


@register_command(
    ["/goal"],
    description="Set a standing goal the agent works toward across turns",
    usage="/goal <objective> | /goal status | pause | resume | clear",
    surfaces=["cli", "frontend", "social"],
    category="session",
)
def handle_goal(
    ctx: typer.Context,
    args: list[str] = typer.Argument(
        None, help="An objective, or a subcommand: status, pause, resume, clear"
    ),
):
    async def _impl():
        from suzent.config import CONFIG
        from suzent.database import get_database
        from suzent.core.goals import (
            STATUS_ACTIVE,
            STATUS_PAUSED,
            format_status,
        )

        cmd_ctx: CommandContext = ctx.obj
        chat_id = cmd_ctx.chat_id
        user_id = cmd_ctx.user_id
        tokens = list(args or [])
        sub = tokens[0].lower() if tokens else "status"

        db = get_database()
        project_id = _resolve_project_id(chat_id)
        if not project_id:
            return "This chat is not linked to a project, so goals are unavailable."

        if not tokens or sub == "status":
            return format_status(db.get_goal(project_id, chat_id=chat_id))

        if sub == "pause":
            goal = db.get_goal(project_id, chat_id=chat_id)
            if not goal or goal.status != STATUS_ACTIVE:
                return "No active goal to pause."
            db.update_goal(goal.id, status=STATUS_PAUSED)
            return "⏸ Goal paused. Use `/goal resume` to continue."

        if sub == "resume":
            goal = db.get_goal(project_id, chat_id=chat_id)
            if not goal:
                return "No goal to resume. Set one with `/goal <objective>`."
            db.update_goal(goal.id, status=STATUS_ACTIVE, turns_elapsed=0)
            _schedule_step(chat_id, user_id)
            return f"▶ Goal resumed:\n  {goal.objective}"

        if sub == "clear":
            if not db.get_goal(project_id, chat_id=chat_id):
                return "No active goal to clear."
            db.clear_goal(project_id, chat_id=chat_id)
            return "🗑 Goal cleared."

        # Otherwise the whole argument is a new objective.
        objective = " ".join(tokens).strip()
        if not objective:
            return "Usage: `/goal <objective>`"
        max_turns = CONFIG.goals_max_turns
        existing = db.get_goal(project_id, chat_id=chat_id)
        if existing:
            db.update_goal(
                existing.id,
                objective=objective,
                status=STATUS_ACTIVE,
                turns_elapsed=0,
                max_turns=max_turns,
            )
        else:
            db.create_goal(
                project_id, objective, chat_id=chat_id, max_turns=max_turns
            )
        _schedule_step(chat_id, user_id)
        return (
            f"🎯 Goal set: {objective}\n"
            f"Working autonomously toward it (max {max_turns} turns). "
            "Use `/goal status` to check, `/goal pause` to stop."
        )

    return _impl


@register_command(
    ["/subgoal"],
    description="Append an acceptance criterion to the active goal (no loop reset)",
    usage="/subgoal <text> | /subgoal remove <N> | /subgoal clear",
    surfaces=["cli", "frontend", "social"],
    category="session",
)
def handle_subgoal(
    ctx: typer.Context,
    args: list[str] = typer.Argument(
        None, help="A criterion, or: remove <N>, clear"
    ),
):
    async def _impl():
        from suzent.database import get_database

        cmd_ctx: CommandContext = ctx.obj
        chat_id = cmd_ctx.chat_id
        tokens = list(args or [])

        db = get_database()
        project_id = _resolve_project_id(chat_id)
        if not project_id:
            return "This chat is not linked to a project, so goals are unavailable."

        goal = db.get_goal(project_id, chat_id=chat_id)
        if not goal:
            return "No active goal. Set one first with `/goal <objective>`."

        subgoals = list(goal.subgoals or [])

        if not tokens:
            if not subgoals:
                return "No sub-goals. Add one with `/subgoal <text>`."
            listing = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(subgoals))
            return f"Sub-goals for the active goal:\n{listing}"

        sub = tokens[0].lower()

        if sub == "clear":
            db.update_goal(goal.id, subgoals=[])
            return "🗑 All sub-goals cleared."

        if sub == "remove":
            if len(tokens) < 2 or not tokens[1].isdigit():
                return "Usage: `/subgoal remove <N>`"
            idx = int(tokens[1]) - 1
            if idx < 0 or idx >= len(subgoals):
                return f"No sub-goal #{tokens[1]}."
            removed = subgoals.pop(idx)
            db.update_goal(goal.id, subgoals=subgoals)
            return f"🗑 Removed sub-goal: {removed}"

        text = " ".join(tokens).strip()
        subgoals.append(text)
        db.update_goal(goal.id, subgoals=subgoals)
        return f"➕ Sub-goal added (#{len(subgoals)}): {text}"

    return _impl
