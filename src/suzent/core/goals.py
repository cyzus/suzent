"""
Goal mode: judge-driven automatic continuation on top of the project Goal system.

The canonical goal store is ``GoalModel`` (project + chat scoped), also driven
by the ``manage_goal`` tool, the per-turn ``plan_reminder_hook`` (which injects
the active goal and increments ``turns_elapsed``), and surfaced in the frontend
right sidebar. This module adds the piece that store lacks: a standing-goal
*continuation loop* — after each non-heartbeat turn an auxiliary **judge** model
(a single, stateless LLM call — never a full agent) decides whether the goal is
satisfied, and if not, automatically runs the agent again until it is done or the
turn budget is exhausted.

    /goal <text>            -> run_goal_step (turn 1)
    turn completes          -> maybe_continue_goal (judge)
        verdict DONE        -> status = completed
        verdict CONTINUE    -> run_goal_step (next turn)
        budget exhausted    -> status = paused

Turn counting is owned by ``plan_reminder_hook`` (it increments ``turns_elapsed``
each turn); this module only *reads* the budget. State, status, and subgoals all
live on ``GoalModel`` so the sidebar and the ``manage_goal`` tool stay in sync.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from suzent.database import get_database
from suzent.logger import get_logger

logger = get_logger(__name__)

# GoalModel statuses.
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

# Consecutive judge parse failures tolerated before auto-pausing. Tracked in
# memory (keyed by goal id) — it is a transient safety valve, not durable state.
MAX_PARSE_FAILURES = 3
_parse_failures: dict[int, int] = {}


JUDGE_SYSTEM_PROMPT = (
    "You are a strict goal-completion judge for an autonomous AI agent. "
    "You are given a goal (and optional sub-goals) plus the agent's most recent "
    "response. Your only job is to decide whether the goal is FULLY satisfied by "
    "the work done so far. Be strict: require concrete evidence of completion, "
    "not promises, intentions, or partial progress. When sub-goals are present, "
    "the goal is done only when the main goal AND every sub-goal are satisfied. "
    "Reply with a single line of minified JSON and nothing else: "
    '{"done": <true|false>, "reason": "<one short sentence>"}.'
)


# ─── Goal resolution (canonical GoalModel store) ─────────────────────────────


def resolve_goal(chat_id: str):
    """Return (project_id, GoalModel) for the chat's active/paused goal, or None."""
    try:
        db = get_database()
        project_id = db.get_chat_project_id(chat_id)
        if not project_id:
            return None
        goal = db.get_goal(project_id, chat_id=chat_id)
        if not goal:
            return None
        return project_id, goal
    except Exception as e:
        logger.debug(f"[goal] resolve_goal failed for {chat_id}: {e}")
        return None


# ─── Judge (single stateless LLM call) ───────────────────────────────────────


def _parse_verdict(raw: str) -> Optional[tuple[bool, str]]:
    """Parse a judge response into (done, reason), or None if unparseable."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # Find the first JSON object in the response (judges sometimes add prose).
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict) or "done" not in data:
        return None
    done = data.get("done")
    if isinstance(done, str):
        done = done.strip().lower() in {"true", "yes", "1"}
    reason = str(data.get("reason", "")).strip()
    return bool(done), reason


def _build_judge_user_prompt(
    objective: str, subgoals: list[str], last_response: str
) -> str:
    parts = [f"GOAL:\n{objective}"]
    if subgoals:
        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(subgoals))
        parts.append(
            "SUB-GOALS (all must be satisfied, with concrete evidence):\n" + numbered
        )
    parts.append("AGENT'S LATEST RESPONSE:\n" + (last_response or "")[:4000])
    parts.append(f"Current time: {datetime.now(timezone.utc).isoformat()}")
    parts.append("Is the goal fully satisfied? Respond with JSON only.")
    return "\n\n".join(parts)


async def judge_goal(
    objective: str, subgoals: list[str], last_response: str
) -> tuple[str, str, bool]:
    """Ask the judge model whether the goal is satisfied.

    Returns ``(verdict, reason, parse_failed)`` where verdict is ``"done"`` or
    ``"continue"``. Both parse failures and transport errors fail OPEN (continue)
    so a flaky judge never wedges progress — the turn budget is the real backstop.
    Only genuine parse failures set ``parse_failed`` (which drives the auto-pause
    after repeated unparseable verdicts).
    """
    from suzent.core.role_router import get_role_router
    from suzent.llm import LLMClient

    model = get_role_router().get_model_id("cheap")
    if not model:
        logger.warning("[goal] no judge model configured; failing open (continue)")
        return "continue", "no judge model configured", True

    try:
        raw = await LLMClient(model=model).complete(
            prompt=_build_judge_user_prompt(objective, subgoals, last_response),
            system=JUDGE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=200,
            reasoning_effort="none",
        )
    except Exception as e:
        logger.warning(f"[goal] judge call failed ({e}); failing open (continue)")
        return "continue", f"judge error: {e}", False

    parsed = _parse_verdict(raw)
    if parsed is None:
        logger.warning(f"[goal] unparseable judge verdict: {raw!r}")
        return "continue", "unparseable judge response", True

    done, reason = parsed
    return ("done" if done else "continue"), reason, False


# ─── Continuation loop ───────────────────────────────────────────────────────


CONTINUATION_PROMPT = (
    "[Goal mode] You are autonomously continuing toward your active goal (shown "
    "in the goal reminder above). Do not wait for the user — take the next "
    "concrete action now. When the goal is fully achieved, call "
    "manage_goal(action='clear'); if you cannot make progress, call "
    "manage_goal(action='pause') and explain why."
)


def _budget_exhausted(goal) -> bool:
    return bool(goal.max_turns) and goal.turns_elapsed >= goal.max_turns


def _goal_config_override() -> dict:
    """Config for autonomous goal turns using headless Auto mode."""
    from suzent.agent_manager import build_agent_config

    base: dict = {
        "memory_enabled": True,
        "permission_mode": "auto",
        "interaction_profile": "headless",
    }
    return build_agent_config(base, require_social_tool=False)


def notify_goal(chat_id: str, message: str) -> None:
    """Surface a goal status line via the scheduler notification deque (status bar)."""
    try:
        from suzent.core.scheduler import get_active_scheduler

        scheduler = get_active_scheduler()
        if scheduler is not None:
            scheduler.add_notification("goal", f"{chat_id[:8]}: {message}")
    except Exception:
        pass
    logger.info(f"[goal] {chat_id}: {message}")


async def run_goal_step(chat_id: str, user_id: str) -> None:
    """Run one autonomous turn toward the active goal, if appropriate."""
    from suzent.core.stream_registry import stream_controls

    resolved = resolve_goal(chat_id)
    if not resolved:
        return
    _project_id, goal = resolved
    if goal.status != STATUS_ACTIVE:
        return

    # Another turn is already streaming for this chat (e.g. a real user message).
    # Let that turn drive the loop instead so we never run two turns at once.
    if chat_id in stream_controls:
        logger.debug(f"[goal] step skipped for {chat_id}: stream already active")
        return

    if _budget_exhausted(goal):
        get_database().update_goal(goal.id, status=STATUS_PAUSED)
        notify_goal(
            chat_id,
            f"⏸ Goal paused — {goal.turns_elapsed}/{goal.max_turns} turns used. "
            "Use /goal resume to continue.",
        )
        return

    turns_label = (
        f"{goal.turns_elapsed + 1}/{goal.max_turns}"
        if goal.max_turns
        else str(goal.turns_elapsed + 1)
    )
    notify_goal(chat_id, f"↻ Continuing toward goal ({turns_label})")

    try:
        from suzent.core.chat_processor import ChatProcessor

        await ChatProcessor().process_background_turn(
            chat_id=chat_id,
            user_id=user_id,
            message_content="",
            config_override=_goal_config_override(),
            system_reminders=[CONTINUATION_PROMPT],
        )
    except Exception as e:
        logger.error(f"[goal] step execution failed for {chat_id}: {e}")


def schedule_goal_step(chat_id: str, user_id: str) -> None:
    """Kick off the first/next autonomous goal turn as a background task.

    Defers until any in-progress stream for this chat has finished so the
    first goal turn never races with a still-emitting command-response or
    foreground stream (which would otherwise be terminated when this turn
    registers its own background stream). The 30 s caps are safety valves.
    """
    import asyncio
    import uuid

    from suzent.core.task_registry import register_background_task

    async def _deferred() -> None:
        from suzent.core.stream_registry import background_queues, stream_controls

        ctrl = stream_controls.get(chat_id)
        if ctrl is not None:
            try:
                await asyncio.wait_for(ctrl.completed_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass

        bq = background_queues.get(chat_id)
        if bq is not None and bq.producer_active:
            try:
                await asyncio.wait_for(bq.done_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass

        await run_goal_step(chat_id, user_id)

    coro = _deferred()
    try:
        asyncio.create_task(
            register_background_task(
                coro,
                task_id=f"goal_step_{chat_id}_{uuid.uuid4().hex}",
                description=f"Goal step for chat {chat_id}",
            )
        )
    except Exception:
        coro.close()


async def maybe_continue_goal(
    chat_id: str, user_id: str, last_response: str, was_cancelled: bool
) -> None:
    """Post-turn hook: judge the goal and auto-continue or finish.

    Called after every non-heartbeat turn. A cheap no-op unless a goal is active.
    """
    resolved = resolve_goal(chat_id)
    if not resolved:
        return
    _project_id, goal = resolved
    if goal.status != STATUS_ACTIVE:
        return

    # User interrupted this turn (steer / stop). Halt the loop but keep the goal
    # active; the next real user turn (or /goal resume) re-enters the loop.
    if was_cancelled:
        logger.debug(f"[goal] continuation halted for {chat_id}: turn was cancelled")
        return

    db = get_database()
    verdict, reason, parse_failed = await judge_goal(
        goal.objective, list(goal.subgoals or []), last_response
    )

    if parse_failed:
        count = _parse_failures.get(goal.id, 0) + 1
        _parse_failures[goal.id] = count
        if count >= MAX_PARSE_FAILURES:
            _parse_failures.pop(goal.id, None)
            db.update_goal(goal.id, status=STATUS_PAUSED)
            notify_goal(
                chat_id,
                "⏸ Goal paused — the judge model returned unparseable verdicts "
                f"{count}× in a row. Configure a stronger 'cheap' model, then "
                "/goal resume.",
            )
            return
        await run_goal_step(chat_id, user_id)  # fail open: keep going
        return

    _parse_failures.pop(goal.id, None)

    if verdict == "done":
        db.update_goal(
            goal.id,
            status=STATUS_COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
        notify_goal(chat_id, f"✓ Goal achieved: {reason}")
        return

    if _budget_exhausted(goal):
        db.update_goal(goal.id, status=STATUS_PAUSED)
        notify_goal(
            chat_id,
            f"⏸ Goal paused — {goal.turns_elapsed}/{goal.max_turns} turns used. "
            "Use /goal resume to continue.",
        )
        return

    await run_goal_step(chat_id, user_id)


# ─── Display helper (for /goal status) ───────────────────────────────────────


def format_status(goal) -> str:
    """Render a human-readable status block for /goal status (takes a GoalModel)."""
    if not goal or goal.status in (STATUS_COMPLETED, STATUS_CANCELLED):
        return "No active goal. Set one with `/goal <objective>`."

    icon = {STATUS_ACTIVE: "🎯", STATUS_PAUSED: "⏸"}.get(goal.status, "🎯")
    turns = (
        f"{goal.turns_elapsed}/{goal.max_turns}"
        if goal.max_turns
        else str(goal.turns_elapsed)
    )
    lines = [
        f"{icon} **Goal** ({goal.status}) — turn {turns}",
        f"  {goal.objective}",
    ]
    if goal.subgoals:
        lines.append("  Sub-goals:")
        lines.extend(f"    {i + 1}. {s}" for i, s in enumerate(goal.subgoals))
    return "\n".join(lines)
