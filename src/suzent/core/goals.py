"""
Goal mode: persistent, self-continuing objectives ("Ralph loop").

A goal is a standing objective the agent works toward across multiple turns
without the user re-prompting each time. After every non-heartbeat turn an
auxiliary *judge* model (a single, stateless LLM call — never a full agent) is
asked whether the goal is fully satisfied. If not, and the turn budget is not
exhausted, the agent is automatically run again with a continuation prompt.

State lives in ``chat.config["goal"]`` so it survives restarts and resumes,
exactly like the heartbeat configuration. Control flow:

    /goal <text>            -> run_goal_step (turn 1)
    turn completes          -> maybe_continue_goal (judge)
        verdict DONE        -> status = done
        verdict CONTINUE    -> run_goal_step (turn N+1)
        budget exhausted    -> status = paused

Any real user turn also passes through ``maybe_continue_goal``, so a manual
message naturally preempts and then re-drives the loop.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger

logger = get_logger(__name__)

GOAL_CONFIG_KEY = "goal"

# Status values for a goal.
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_DONE = "done"
STATUS_CLEARED = "cleared"

# Consecutive judge parse failures tolerated before auto-pausing and asking the
# user to configure a stronger judge model.
MAX_PARSE_FAILURES = 3


JUDGE_SYSTEM_PROMPT = (
    "You are a strict goal-completion judge for an autonomous AI agent. "
    "You are given a goal (and optional sub-goals) plus the agent's most recent "
    "response. Your only job is to decide whether the goal is FULLY satisfied by "
    "the work done so far. Be strict: require concrete evidence of completion, "
    "not promises, intentions, or partial progress. When sub-goals are present, "
    "the goal is done only when the main goal AND every sub-goal are satisfied. "
    'Reply with a single line of minified JSON and nothing else: '
    '{"done": <true|false>, "reason": "<one short sentence>"}.'
)


@dataclass
class GoalState:
    """Persistent state for a single chat's standing goal."""

    objective: str
    status: str = STATUS_ACTIVE
    turn: int = 0
    max_turns: int = 20
    subgoals: list[str] = field(default_factory=list)
    parse_failures: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Optional["GoalState"]:
        if not isinstance(data, dict) or not data.get("objective"):
            return None
        return cls(
            objective=str(data.get("objective", "")),
            status=str(data.get("status", STATUS_ACTIVE)),
            turn=int(data.get("turn", 0) or 0),
            max_turns=int(data.get("max_turns", CONFIG.goals_max_turns) or 0),
            subgoals=[str(s) for s in (data.get("subgoals") or [])],
            parse_failures=int(data.get("parse_failures", 0) or 0),
        )


# ─── Persistence ───────────────────────────────────────────────────────────


def get_goal(chat_id: str) -> Optional[GoalState]:
    """Load the goal state for a chat, or None if none is set."""
    try:
        chat = get_database().get_chat(chat_id)
    except Exception as e:
        logger.debug(f"[goal] get_goal failed for {chat_id}: {e}")
        return None
    if not chat:
        return None
    return GoalState.from_dict((chat.config or {}).get(GOAL_CONFIG_KEY))


def save_goal(chat_id: str, state: GoalState) -> None:
    """Persist goal state into ``chat.config['goal']``."""
    try:
        get_database().merge_chat_config(chat_id, {GOAL_CONFIG_KEY: state.to_dict()})
    except Exception as e:
        logger.warning(f"[goal] save_goal failed for {chat_id}: {e}")


def clear_goal(chat_id: str) -> None:
    """Remove the goal from a chat's config."""
    try:
        state = get_goal(chat_id)
        if state is None:
            return
        state.status = STATUS_CLEARED
        # Keep the record but mark it cleared so /goal status reads cleanly,
        # then drop the heavy fields by overwriting with a minimal marker.
        get_database().merge_chat_config(
            chat_id, {GOAL_CONFIG_KEY: {"objective": "", "status": STATUS_CLEARED}}
        )
    except Exception as e:
        logger.warning(f"[goal] clear_goal failed for {chat_id}: {e}")


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


def _build_continuation_prompt(state: GoalState) -> str:
    parts = [
        f"[Goal mode — step {state.turn}/{state.max_turns}] "
        "You are autonomously working toward a standing goal. Do not ask the user "
        "for confirmation or wait for further input — take the next concrete action "
        "yourself. When the goal is fully achieved, state clearly that it is complete.",
        f"GOAL:\n{state.objective}",
    ]
    if state.subgoals:
        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(state.subgoals))
        parts.append("SUB-GOALS (all must be satisfied):\n" + numbered)
    parts.append("Continue now with the next concrete step.")
    return "\n\n".join(parts)


def _goal_config_override() -> dict:
    """Config for autonomous goal turns: auto-approve tools, memory on."""
    from suzent.agent_manager import build_agent_config

    base: dict = {"memory_enabled": True, "auto_approve_tools": True}
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

    state = get_goal(chat_id)
    if not state or state.status != STATUS_ACTIVE:
        return

    # Another turn is already streaming for this chat (e.g. a real user message).
    # Let that turn drive the loop instead so we never run two turns at once.
    if chat_id in stream_controls:
        logger.debug(f"[goal] step skipped for {chat_id}: stream already active")
        return

    if state.turn >= state.max_turns:
        state.status = STATUS_PAUSED
        save_goal(chat_id, state)
        notify_goal(
            chat_id,
            f"⏸ Goal paused — {state.turn}/{state.max_turns} turns used. "
            "Use /goal resume to continue.",
        )
        return

    state.turn += 1
    save_goal(chat_id, state)
    notify_goal(chat_id, f"↻ Continuing toward goal ({state.turn}/{state.max_turns})")

    prompt = _build_continuation_prompt(state)
    try:
        from suzent.core.chat_processor import ChatProcessor

        await ChatProcessor().process_background_turn(
            chat_id=chat_id,
            user_id=user_id,
            message_content="",
            config_override=_goal_config_override(),
            system_reminders=[prompt],
        )
    except Exception as e:
        logger.error(f"[goal] step execution failed for {chat_id}: {e}")


async def maybe_continue_goal(
    chat_id: str, user_id: str, last_response: str, was_cancelled: bool
) -> None:
    """Post-turn hook: judge the goal and auto-continue or finish.

    Called after every non-heartbeat turn. A cheap no-op unless a goal is active.
    """
    state = get_goal(chat_id)
    if not state or state.status != STATUS_ACTIVE:
        return

    # User interrupted this turn (steer / stop). Halt the loop but keep the goal
    # active; the next real user turn (or /goal resume) re-enters the loop.
    if was_cancelled:
        logger.debug(f"[goal] continuation halted for {chat_id}: turn was cancelled")
        return

    verdict, reason, parse_failed = await judge_goal(
        state.objective, state.subgoals, last_response
    )

    if parse_failed:
        state.parse_failures += 1
        if state.parse_failures >= MAX_PARSE_FAILURES:
            state.status = STATUS_PAUSED
            save_goal(chat_id, state)
            notify_goal(
                chat_id,
                "⏸ Goal paused — the judge model returned unparseable verdicts "
                f"{state.parse_failures}× in a row. Configure a stronger 'cheap' "
                "model, then /goal resume.",
            )
            return
        save_goal(chat_id, state)
        await run_goal_step(chat_id, user_id)  # fail open: keep going
        return

    state.parse_failures = 0

    if verdict == "done":
        state.status = STATUS_DONE
        save_goal(chat_id, state)
        notify_goal(chat_id, f"✓ Goal achieved: {reason}")
        return

    save_goal(chat_id, state)
    await run_goal_step(chat_id, user_id)


# ─── Display helpers ─────────────────────────────────────────────────────────


def format_status(state: Optional[GoalState]) -> str:
    """Render a human-readable status block for /goal status."""
    if not state or not state.objective or state.status == STATUS_CLEARED:
        return "No active goal. Set one with `/goal <objective>`."

    icon = {
        STATUS_ACTIVE: "🎯",
        STATUS_PAUSED: "⏸",
        STATUS_DONE: "✓",
    }.get(state.status, "🎯")

    lines = [
        f"{icon} **Goal** ({state.status}) — turn {state.turn}/{state.max_turns}",
        f"  {state.objective}",
    ]
    if state.subgoals:
        lines.append("  Sub-goals:")
        lines.extend(f"    {i + 1}. {s}" for i, s in enumerate(state.subgoals))
    return "\n".join(lines)
