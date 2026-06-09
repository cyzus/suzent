"""Goal-mode slash commands: /goal and /subgoal."""

import typer

from suzent.core.commands.base import register_command, CommandContext

_RESERVED = {"status", "pause", "resume", "clear"}


def _schedule_step(chat_id: str, user_id: str) -> None:
    """Kick off the first/next autonomous goal turn as a background task."""
    import uuid
    from suzent.core.goals import run_goal_step
    from suzent.core.task_registry import register_background_task

    coro = run_goal_step(chat_id, user_id)
    try:
        import asyncio

        asyncio.create_task(
            register_background_task(
                coro,
                task_id=f"goal_step_{chat_id}_{uuid.uuid4().hex}",
                description=f"Goal step for chat {chat_id}",
            )
        )
    except Exception:
        coro.close()


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
        from suzent.core.goals import (
            GoalState,
            STATUS_ACTIVE,
            STATUS_DONE,
            STATUS_PAUSED,
            STATUS_CLEARED,
            get_goal,
            save_goal,
            clear_goal,
            format_status,
        )

        cmd_ctx: CommandContext = ctx.obj
        chat_id = cmd_ctx.chat_id
        user_id = cmd_ctx.user_id
        tokens = list(args or [])
        sub = tokens[0].lower() if tokens else "status"

        if not tokens or sub == "status":
            return format_status(get_goal(chat_id))

        if sub == "pause":
            state = get_goal(chat_id)
            if not state or state.status not in (STATUS_ACTIVE,):
                return "No active goal to pause."
            state.status = STATUS_PAUSED
            save_goal(chat_id, state)
            return "⏸ Goal paused. Use `/goal resume` to continue."

        if sub == "resume":
            state = get_goal(chat_id)
            if not state or state.status == STATUS_CLEARED:
                return "No goal to resume. Set one with `/goal <objective>`."
            if state.status == STATUS_DONE:
                return "Goal already completed. Set a new one with `/goal <objective>`."
            state.status = STATUS_ACTIVE
            state.turn = 0
            state.parse_failures = 0
            save_goal(chat_id, state)
            _schedule_step(chat_id, user_id)
            return f"▶ Goal resumed (max {state.max_turns} turns):\n  {state.objective}"

        if sub == "clear":
            clear_goal(chat_id)
            return "🗑 Goal cleared."

        # Otherwise the whole argument is a new objective.
        objective = " ".join(tokens).strip()
        if not objective:
            return "Usage: `/goal <objective>`"
        state = GoalState(
            objective=objective,
            status=STATUS_ACTIVE,
            turn=0,
            max_turns=CONFIG.goals_max_turns,
            subgoals=[],
        )
        save_goal(chat_id, state)
        _schedule_step(chat_id, user_id)
        return (
            f"🎯 Goal set: {objective}\n"
            f"Working autonomously toward it (max {state.max_turns} turns). "
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
        from suzent.core.goals import STATUS_CLEARED, get_goal, save_goal

        cmd_ctx: CommandContext = ctx.obj
        chat_id = cmd_ctx.chat_id
        tokens = list(args or [])

        state = get_goal(chat_id)
        if not state or state.status == STATUS_CLEARED or not state.objective:
            return "No active goal. Set one first with `/goal <objective>`."

        if not tokens:
            if not state.subgoals:
                return "No sub-goals. Add one with `/subgoal <text>`."
            listing = "\n".join(
                f"  {i + 1}. {s}" for i, s in enumerate(state.subgoals)
            )
            return f"Sub-goals for the active goal:\n{listing}"

        sub = tokens[0].lower()

        if sub == "clear":
            state.subgoals = []
            save_goal(chat_id, state)
            return "🗑 All sub-goals cleared."

        if sub == "remove":
            if len(tokens) < 2 or not tokens[1].isdigit():
                return "Usage: `/subgoal remove <N>`"
            idx = int(tokens[1]) - 1
            if idx < 0 or idx >= len(state.subgoals):
                return f"No sub-goal #{tokens[1]}."
            removed = state.subgoals.pop(idx)
            save_goal(chat_id, state)
            return f"🗑 Removed sub-goal: {removed}"

        text = " ".join(tokens).strip()
        state.subgoals.append(text)
        save_goal(chat_id, state)
        return f"➕ Sub-goal added (#{len(state.subgoals)}): {text}"

    return _impl
