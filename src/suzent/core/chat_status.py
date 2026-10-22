"""Where each chat stands for the user: waiting on them, running, idle or resolved.

The user owns one thing, resolving a chat. Everything else is read from what
the chat is doing: a question or approval it holds open, a task stuck on the
user, and, after each turn, the Decision model's read of whether the reply
leaves the next move to the user. Tasks stay the agent's own bookkeeping.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from suzent.database import get_database
from suzent.logger import get_logger

logger = get_logger(__name__)

type ChatState = Literal["waiting", "running", "idle", "resolved"]
type WaitingKind = Literal["question", "approval", "task", "reply"]

STATES: tuple[ChatState, ...] = ("waiting", "running", "idle", "resolved")
# Idle and resolved chats drop off the board once they have been quiet this long.
RECENT_WINDOW = timedelta(days=7)
BOARD_SCAN_LIMIT = 300
SUMMARY_MAX_CHARS = 160
REASON_MAX_CHARS = 120

JUDGE_SYSTEM_PROMPT = (
    "You read the end of an AI agent's turn in a conversation with its user and "
    "report where things stand.\n"
    "waiting_on_user: true only when the agent cannot go on without the user: it "
    "asked a question, wants a decision or approval, or needs something only the "
    "user can provide. false when it finished, reported progress, or will carry "
    "on by itself. A closing offer such as 'let me know if you want more' is not "
    "waiting.\n"
    "reason: when waiting, a short phrase naming what the agent needs from the "
    "user; otherwise an empty string.\n"
    "summary: one plain sentence, at most 120 characters, on where the work "
    "stands now, written in the language the conversation uses.\n"
    'Respond with JSON only: {"waiting_on_user": bool, "reason": str, "summary": str}'
)


def is_tracked(chat_id: str, project_id: Optional[str], config: dict) -> bool:
    """Ordinary project conversations, not Regent, sub-agents, chat apps or dreams."""
    from suzent.core.focal_agent import is_focal_chat_id

    return (
        bool(project_id)
        and not is_focal_chat_id(chat_id)
        and not config.get("platform")
    )


def is_tracked_chat(chat: Any) -> bool:
    return chat is not None and is_tracked(chat.id, chat.project_id, chat.config or {})


def _as_utc(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _clip(text: Any, limit: int) -> Optional[str]:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def _emit_changed(chat_id: str) -> None:
    try:
        from suzent.core.stream_registry import emit_bus_event

        emit_bus_event({"event": "chat_status_changed", "chat_id": chat_id})
    except Exception as exc:
        logger.debug(f"Failed to emit chat status change: {exc}")


# ─── User actions and turn hooks ─────────────────────────────────────────────


def set_resolved(chat_id: str, resolved: bool) -> bool:
    """Resolve the chat for the user, or reopen it. False when the chat is gone."""
    fields: dict[str, Any] = {
        "resolved_at": datetime.now(timezone.utc) if resolved else None
    }
    if resolved:
        fields["waiting_on_user"] = False
        fields["waiting_reason"] = None
    row = get_database().update_chat_status(chat_id, **fields)
    if row is None:
        return False
    _emit_changed(chat_id)
    return True


def reopen_on_turn_start(chat_id: str) -> None:
    """A new turn makes the chat active again and the last read of it stale."""
    db = get_database()
    row = db.get_chat_status(chat_id)
    if row is None or (row.resolved_at is None and not row.waiting_on_user):
        return
    db.update_chat_status(
        chat_id, resolved_at=None, waiting_on_user=False, waiting_reason=None
    )
    _emit_changed(chat_id)


def _parse_judgement(raw: str) -> Optional[dict[str, Any]]:
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "waiting_on_user" not in data:
        return None
    return data


async def judge_turn(chat_id: str, user_message: str, reply: str) -> None:
    """Record whether the turn left the next move to the user, with a one-line summary.

    Runs on the Decision model after the turn. Any failure keeps the previous
    record, so the chat simply reads as idle rather than blocking anything.
    """
    from suzent.core.role_router import get_role_router
    from suzent.llm import LLMClient

    model = get_role_router().get_model_id("decision")
    if not model or not reply.strip():
        return
    prompt = (
        f"USER'S LAST MESSAGE:\n{(user_message or '')[:2000]}\n\n"
        f"AGENT'S REPLY:\n{reply[-4000:]}\n\n"
        "Respond with JSON only."
    )
    try:
        raw = await LLMClient(model=model).complete(
            prompt=prompt,
            system=JUDGE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=200,
            reasoning_effort="none",
        )
    except Exception as exc:
        logger.warning(f"[chat_status] judge call failed for {chat_id}: {exc}")
        return
    data = _parse_judgement(raw)
    if data is None:
        logger.warning(f"[chat_status] unparseable judgement for {chat_id}: {raw!r}")
        return
    waiting = bool(data.get("waiting_on_user"))
    fields: dict[str, Any] = {
        "waiting_on_user": waiting,
        "waiting_reason": _clip(data.get("reason"), REASON_MAX_CHARS)
        if waiting
        else None,
        "summary": _clip(data.get("summary"), SUMMARY_MAX_CHARS),
        "judged_at": datetime.now(timezone.utc),
    }
    if waiting:
        fields["resolved_at"] = None
    if get_database().update_chat_status(chat_id, **fields) is not None:
        _emit_changed(chat_id)


# ─── Reading states ──────────────────────────────────────────────────────────


def _pending_question_chats() -> set[str]:
    from suzent.a2ui import pending as pending_questions

    return pending_questions.chats_waiting()


def chat_state(
    *,
    running: bool,
    holds_question: bool,
    holds_approval: bool,
    blocked_task: Optional[Any],
    status: Optional[Any],
) -> tuple[ChatState, Optional[WaitingKind], Optional[str]]:
    """The chat's state, and when waiting, what kind of wait and a short reason.

    A question or approval held open beats running, since the run is parked on
    the user. Resolving is the user's word on everything after that, until a
    new turn or a fresh wait reopens the chat.
    """
    if holds_question:
        return "waiting", "question", None
    if holds_approval:
        return "waiting", "approval", None
    if running:
        return "running", None, None
    if status is not None and status.resolved_at is not None:
        return "resolved", None, None
    if blocked_task is not None:
        return "waiting", "task", blocked_task.waiting_reason
    if status is not None and status.waiting_on_user:
        return "waiting", "reply", status.waiting_reason
    return "idle", None, None


def list_chat_states(project_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Every tracked chat worth a row on the board, newest activity first.

    Waiting and running chats always show; idle and resolved ones only while
    they have been active within ``RECENT_WINDOW``.
    """
    from suzent.core.focal_agent import ATTENTION_WAITING_KINDS, running_chat_ids

    db = get_database()
    projects = {
        project.id: project
        for project in db.list_projects(include_archived=False)
        if project.slug != "social" and (project_id is None or project.id == project_id)
    }
    running = running_chat_ids()
    questions = _pending_question_chats()

    tasks_by_chat: dict[str, list[Any]] = {}
    for pid in projects:
        for task in db.list_tasks(project_id=pid):
            if task.chat_id:
                tasks_by_chat.setdefault(task.chat_id, []).append(task)

    summaries = {
        summary.id: summary
        for summary in db.list_chats(limit=BOARD_SCAN_LIMIT)
        if summary.projectId in projects
    }
    # A chat holding a wait stays on the board however old its last write is.
    for chat_id in (set(tasks_by_chat) | running | questions) - set(summaries):
        chat = db.get_chat(chat_id)
        if chat is not None and chat.project_id in projects:
            summaries[chat_id] = _summary_from_chat(chat, projects)

    statuses = db.list_chat_statuses(list(summaries))
    configs = db.get_chat_configs(list(summaries))
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for chat_id, summary in summaries.items():
        config = configs.get(chat_id, {})
        if not is_tracked(chat_id, summary.projectId, config):
            continue
        tasks = tasks_by_chat.get(chat_id, [])
        blocked = next(
            (
                task
                for task in tasks
                if task.status == "blocked"
                and task.waiting_kind in ATTENTION_WAITING_KINDS
            ),
            None,
        )
        status = statuses.get(chat_id)
        state, waiting_kind, waiting_reason = chat_state(
            running=chat_id in running,
            holds_question=chat_id in questions,
            holds_approval=bool(config.get("_pending_approvals")),
            blocked_task=blocked,
            status=status,
        )
        updated = _as_utc(datetime.fromisoformat(summary.updatedAt))
        if state in ("idle", "resolved") and (
            updated is None or now - updated > RECENT_WINDOW
        ):
            continue
        rows.append(
            {
                "chatId": chat_id,
                "title": summary.title,
                "projectId": summary.projectId,
                "projectName": summary.projectName,
                "state": state,
                "waitingKind": waiting_kind,
                "waitingReason": waiting_reason,
                "summary": (status.summary if status else None)
                or _clip(summary.lastMessage, SUMMARY_MAX_CHARS),
                "lastActiveAt": updated.isoformat() if updated else None,
                "resolvedAt": status.resolved_at.isoformat()
                if status and status.resolved_at
                else None,
                "openTasks": sum(
                    1 for task in tasks if task.status not in ("completed", "cancelled")
                ),
                "doneTasks": sum(1 for task in tasks if task.status == "completed"),
            }
        )
    rows.sort(key=lambda row: row["lastActiveAt"] or "", reverse=True)
    return rows


def _summary_from_chat(chat: Any, projects: dict[str, Any]) -> Any:
    from suzent.database.chats import SUMMARY_LAST_MESSAGE_KEY
    from suzent.database.models import ChatSummaryModel

    project = projects.get(chat.project_id)
    return ChatSummaryModel(
        id=chat.id,
        title=chat.title,
        createdAt=chat.created_at.isoformat(),
        updatedAt=chat.updated_at.isoformat(),
        messageCount=0,
        lastMessage=(chat.config or {}).get(SUMMARY_LAST_MESSAGE_KEY),
        projectId=chat.project_id,
        projectName=project.name if project else None,
    )


def count_states(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {state: 0 for state in STATES}
    for row in rows:
        counts[row["state"]] += 1
    return counts
