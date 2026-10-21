"""The Focal Agent: a singleton SUZENT chat that orchestrates every project.

The Focal Agent is the user's one point of attention. It sees all projects,
dispatches work to project primary sessions, and is woken when one of them
blocks on the user.
"""

import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from suzent.database import ChatModel, get_database
from suzent.logger import get_logger

logger = get_logger(__name__)

FOCAL_CHAT_ID = "focal-suzent"
FOCAL_PLATFORM = "focal"
FOCAL_TITLE = "SUZENT"
ATTENTION_WAITING_KINDS = ("user", "error")

_MAX_CONTEXT_SESSIONS_PER_PROJECT = 10

# The Focal Agent orchestrates; project sessions do the work. It gets no tools
# that change files, run commands or act on a project directly, whatever the
# user's tool picker says.
FOCAL_TOOL_NAMES = (
    "AgentListTool",
    "AgentReadTool",
    "FocalDispatchTool",
    "AgentStopTool",
    "WebSearchTool",
    "WebpageTool",
    "MemorySearchTool",
    "SessionSearchTool",
    "AskQuestionTool",
    "SkillTool",
    "ReadFileTool",
    "GlobTool",
    "GrepTool",
    "FocalScheduleTool",
    "FocalNotesTool",
)

FOCAL_HEARTBEAT_INTERVAL_MINUTES = 30
# A session counts as stalled for the heartbeat only once it has sat idle this
# long with work left, so a session between two turns is not flagged.
STALL_AFTER = timedelta(minutes=30)
# A blocker the user was already told about is raised again only after this.
REMIND_BLOCKED_AFTER = timedelta(hours=2)
DEFAULT_FOCAL_HEARTBEAT = """# SUZENT check-in
- Sessions idle with open tasks: nudge them with agent_dispatch if the next step is clear, otherwise tell the user what is stuck.
- Tasks that have waited on the user for a long time: remind the user once, in one line.
"""
# Earlier built-in checklists, upgraded in place since the user never edited them.
DEFAULT_FOCAL_NOTES = """# SUZENT's notes
How the user wants me to work. Rules only, never project or task status.

## Bring to the user

## Handle without asking

## Don't disturb

## Project names

## Reports
"""
_OVERVIEW_CHARS = 160
_PREVIOUS_FOCAL_HEARTBEATS = (
    DEFAULT_FOCAL_HEARTBEAT.replace("agent_dispatch", "agent_send"),
)


def is_focal_chat(chat: Optional[ChatModel]) -> bool:
    if chat is None:
        return False
    config = getattr(chat, "config", None) or {}
    return (
        getattr(chat, "id", None) == FOCAL_CHAT_ID
        or bool(config.get("is_focal_agent"))
        or str(config.get("platform") or "").lower() == FOCAL_PLATFORM
    )


def is_focal_chat_id(chat_id: Optional[str]) -> bool:
    if not chat_id:
        return False
    if chat_id == FOCAL_CHAT_ID:
        return True
    return is_focal_chat(get_database().get_chat(chat_id))


def apply_focal_tool_policy(config: dict[str, Any], chat_id: Optional[str]) -> None:
    """Pin a Focal Agent turn to its orchestration tools, overriding request config.

    Unchecked tools stay discoverable through ToolSearch, so everything outside
    the set is denied rather than merely left unequipped. MCP servers are off,
    and no working directory or mounted folder is granted: project sessions
    carry their own.
    """
    if not is_focal_chat_id(chat_id):
        return
    from suzent.tools.registry import list_available_tools

    # The fixed orchestration tool set runs without interactive approval.
    config["permission_mode"] = "full_access"
    config["tools"] = list(FOCAL_TOOL_NAMES)
    config["denied_tools"] = [
        name for name in list_available_tools() if name not in FOCAL_TOOL_NAMES
    ]
    config["mcp_disabled"] = True
    config.pop("cwd", None)
    config.pop("sandbox_volumes", None)


def _ensure_focal_project() -> str:
    """The hidden system project that holds the Focal Agent's own files."""
    db = get_database()
    project = db.get_project_by_slug(db.FOCAL_PROJECT_SLUG)
    if project is not None:
        return project.id
    return db.create_project(db.FOCAL_PROJECT_NAME, db.FOCAL_PROJECT_SLUG)


def _ensure_default_heartbeat_file(seed: bool) -> None:
    """Seed the check-in list the user can edit, or upgrade an untouched old one.

    Never overwrites a list the user edited.
    """
    path = get_database().get_project_dir(FOCAL_CHAT_ID) / "heartbeat.md"
    try:
        if path.exists():
            current = path.read_text(encoding="utf-8").strip()
            if current not in {text.strip() for text in _PREVIOUS_FOCAL_HEARTBEATS}:
                return
        elif not seed:
            return
    except OSError as exc:
        logger.warning("Could not read the Focal heartbeat checklist: {}", exc)
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_FOCAL_HEARTBEAT, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write the Focal heartbeat checklist: {}", exc)


def _ensure_notes_file() -> None:
    """Give SUZENT's notes their sections when there are none yet."""
    path = notes_path()
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_FOCAL_NOTES, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write SUZENT's notes: {}", exc)


def notes_path() -> Path:
    """SUZENT's notes: its system project's context.md, loaded as core memory."""
    return get_database().get_project_dir(FOCAL_CHAT_ID) / "context.md"


def get_or_create_focal_chat() -> ChatModel:
    """Return the singleton Focal Agent chat, creating it on first use.

    Also moves a chat created before the system project existed into it, and
    turns the heartbeat on once. After that the heartbeat setting is the
    user's: turning it off sticks.
    """
    db = get_database()
    project_id = _ensure_focal_project()
    chat = db.get_chat(FOCAL_CHAT_ID)
    if chat is None:
        db.create_chat(
            title=FOCAL_TITLE,
            config={"is_focal_agent": True, "platform": FOCAL_PLATFORM},
            chat_id=FOCAL_CHAT_ID,
            project_id=project_id,
        )
        logger.info("Created Focal Agent chat {}", FOCAL_CHAT_ID)
    else:
        if chat.project_id != project_id:
            db.link_chat_to_project(FOCAL_CHAT_ID, project_id)
        # Auto-title once renamed SUZENT after its first topic; put the name back.
        if chat.title != FOCAL_TITLE:
            db.update_chat(FOCAL_CHAT_ID, title=FOCAL_TITLE, reindex=False)
    chat = db.get_chat(FOCAL_CHAT_ID)
    initialized = (chat.config or {}).get("focal_heartbeat_initialized")
    _ensure_default_heartbeat_file(seed=not initialized)
    _ensure_notes_file()
    if not initialized:
        db.merge_chat_config(
            FOCAL_CHAT_ID,
            {
                "heartbeat_enabled": True,
                "heartbeat_interval_minutes": FOCAL_HEARTBEAT_INTERVAL_MINUTES,
                "focal_heartbeat_initialized": True,
            },
        )
        chat = db.get_chat(FOCAL_CHAT_ID)
    return chat


def running_chat_ids() -> set[str]:
    """Chats with a turn in progress, in the foreground or the background."""
    from suzent.core.run_state import is_running
    from suzent.core.stream_registry import (
        background_queues,
        is_background_streaming,
        stream_controls,
    )

    candidates = {*background_queues, *stream_controls}
    return {
        chat_id
        for chat_id in candidates
        if is_background_streaming(chat_id) or is_running(chat_id)
    }


def _needs_attention(task: Any) -> bool:
    return task.status == "blocked" and task.waiting_kind in ATTENTION_WAITING_KINDS


def _format_task(task: Any) -> str:
    line = f"#{task.id} [{task.status}] {task.title}"
    if task.status == "blocked":
        reason = task.waiting_reason or "no reason given"
        line += f" — waiting on {task.waiting_kind or 'unknown'}: {reason}"
        if task.next_action:
            line += f" (next: {task.next_action})"
    elif task.active_form:
        line += f" — {task.active_form}"
    return line


def _project_overview(slug: str) -> Optional[str]:
    """One line from a project's context.md: its Overview, else its first prose line.

    Read live, so SUZENT never keeps a copy of project knowledge that could
    drift from what the project's own sessions maintain.
    """
    from suzent.config import CONFIG

    path = Path(CONFIG.sandbox_data_path) / "projects" / slug / "context.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    in_overview = False
    first_prose = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            in_overview = line.lstrip("#").strip().lower() == "overview"
            continue
        if not line or line.startswith(("<!--", "|", "```")):
            continue
        if in_overview:
            first_prose = line
            break
        first_prose = first_prose or line
    if first_prose is None:
        return None
    summary = first_prose.lstrip("-* ").strip()
    if len(summary) > _OVERVIEW_CHARS:
        summary = summary[: _OVERVIEW_CHARS - 1].rstrip() + "…"
    return summary or None


def build_focal_global_context() -> str:
    """Render the projects, live primary sessions and open tasks the Focal Agent oversees."""
    db = get_database()
    running = running_chat_ids()
    lines = [
        "# SUZENT Global Context",
        "You are SUZENT: the user's single point of attention "
        "across every project. Converse naturally with the user. When they ask "
        "for project work, dispatch it to a Project Primary Session instead of "
        "doing it here: wake an existing session with "
        "`agent_dispatch(agent_id=<session id>, message=...)`, or start a new one with "
        "`agent_dispatch(agent_id='new', project_id=<id or slug>, title=..., "
        "task_title=..., message=...)`. Primary sessions run autonomously and "
        "notify you when they block on the user; relay those blockers clearly.",
        "",
        "## Projects",
    ]
    projects = db.list_projects(include_archived=False)
    if not projects:
        lines.append("(no projects)")
    for project in projects:
        line = f"- {project.name} · slug `{project.slug}` · id `{project.id}`"
        overview = _project_overview(project.slug)
        lines.append(f"{line} — {overview}" if overview else line)
        tasks = db.list_tasks(project_id=project.id)
        by_chat: dict[Optional[str], list[Any]] = {}
        for task in tasks:
            by_chat.setdefault(task.chat_id, []).append(task)
        session_ids = [chat_id for chat_id in by_chat if chat_id]
        session_ids += [
            chat_id
            for chat_id in sorted(running)
            if chat_id not in by_chat
            and chat_id != FOCAL_CHAT_ID
            and (chat := db.get_chat(chat_id)) is not None
            and chat.project_id == project.id
        ]
        session_ids.sort(
            key=lambda chat_id: (
                not any(_needs_attention(task) for task in by_chat.get(chat_id, [])),
                chat_id not in running,
            )
        )
        for chat_id in session_ids[:_MAX_CONTEXT_SESSIONS_PER_PROJECT]:
            chat = db.get_chat(chat_id)
            if chat is None or is_focal_chat(chat):
                continue
            state = "running" if chat_id in running else "idle"
            lines.append(
                f"  - Session `{chat_id}` · {chat.title or 'Untitled'} · {state}"
            )
            lines.extend(
                f"    - {_format_task(task)}" for task in by_chat.get(chat_id, [])
            )
        omitted = len(session_ids) - _MAX_CONTEXT_SESSIONS_PER_PROJECT
        if omitted > 0:
            lines.append(f"  - … {omitted} more sessions (use agent_list)")
        unbound = by_chat.get(None, [])
        if unbound:
            lines.append("  - Unassigned tasks:")
            lines.extend(f"    - {_format_task(task)}" for task in unbound)
    return "\n".join(lines)


def _last_activity(chat: Optional[ChatModel]) -> Optional[str]:
    """When SUZENT last said something, from a user turn or a background one."""
    if chat is None:
        return None
    # SQLite drops the zone: turns stamp local time, background runs stamp UTC.
    moments = []
    if chat.last_active_at is not None:
        active = chat.last_active_at
        moments.append(active if active.tzinfo else active.astimezone())
    if chat.last_result_at is not None:
        result = chat.last_result_at
        moments.append(result if result.tzinfo else result.replace(tzinfo=timezone.utc))
    return max(moments).isoformat() if moments else None


def focal_status() -> dict[str, Any]:
    """Telemetry for the Focal Agent presence card."""
    db = get_database()
    running = running_chat_ids() - {FOCAL_CHAT_ID}
    waiting = 0
    waiting_by_project: dict[str, int] = {}
    waiting_by_chat: dict[str, int] = {}
    auto_run: set[str] = set()
    by_chat: dict[str, list[Any]] = {}
    for project in db.list_projects(include_archived=False):
        for task in db.list_tasks(project_id=project.id):
            if _needs_attention(task):
                waiting += 1
                waiting_by_project[project.id] = (
                    waiting_by_project.get(project.id, 0) + 1
                )
                if task.chat_id:
                    waiting_by_chat[task.chat_id] = (
                        waiting_by_chat.get(task.chat_id, 0) + 1
                    )
            if task.chat_id and task.chat_id in running:
                auto_run.add(task.chat_id)
            if task.chat_id:
                by_chat.setdefault(task.chat_id, []).append(task)
    # Same rule as the board: not running, work left, nothing waiting on the user.
    stalled = sum(
        1
        for chat_id, tasks in by_chat.items()
        if chat_id not in running
        and any(task.status in ("pending", "in_progress") for task in tasks)
        and not any(_needs_attention(task) for task in tasks)
    )
    for chat_id in running - auto_run:
        chat = db.get_chat(chat_id)
        if chat is not None and (chat.config or {}).get("spawned_by_focal"):
            auto_run.add(chat_id)
    from suzent.database.chats import SUMMARY_LAST_MESSAGE_KEY

    focal = db.get_chat(FOCAL_CHAT_ID)
    config = (focal.config or {}) if focal else {}
    return {
        "chatId": FOCAL_CHAT_ID,
        "title": FOCAL_TITLE,
        "waiting": waiting,
        "autoRun": len(auto_run),
        "stalled": stalled,
        # The sidebar marks projects and sessions holding work that waits on the user.
        "waitingByProject": waiting_by_project,
        "waitingByChat": waiting_by_chat,
        "running": FOCAL_CHAT_ID in running_chat_ids(),
        # New messages from background check-ins, wake-ups and events show on
        # SUZENT's card rather than as tasks in the sidebar.
        "unread": int(config.get("unread_count") or 0),
        "lastMessage": config.get(SUMMARY_LAST_MESSAGE_KEY),
        "lastMessageAt": _last_activity(focal),
    }


def notify_focal_of_blocked_task(task: Any, chat_id: str) -> bool:
    """Wake the Focal Agent about a task that now waits on the user."""
    if chat_id == FOCAL_CHAT_ID:
        return False
    db = get_database()
    chat = db.get_chat(chat_id)
    spawned_by_focal = bool(
        chat and (chat.config or {}).get("parent_chat_id") == FOCAL_CHAT_ID
    )
    if not spawned_by_focal and db.get_chat(FOCAL_CHAT_ID) is None:
        return False
    get_or_create_focal_chat()
    project = db.get_project(task.project_id)
    project_name = project.name if project else task.project_id
    session_title = chat.title if chat else chat_id
    content = "\n".join(
        [
            f"Task blocked in project {project_name}.",
            f"Session: {session_title} (`{chat_id}`)",
            f"Task #{task.id}: {task.title}",
            f"Waiting on: {task.waiting_kind}",
            f"Reason: {task.waiting_reason or 'not given'}",
            f"Next action: {task.next_action or 'not given'}",
        ]
    )
    from suzent.core.agent_inbox import enqueue_agent_message

    try:
        enqueue_agent_message(
            target_chat_id=FOCAL_CHAT_ID,
            sender_chat_id=chat_id,
            content=content,
            kind="task_blocked_notification",
            payload={
                "project_id": task.project_id,
                "task_id": task.id,
                "waiting_kind": task.waiting_kind,
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to notify Focal Agent of blocked task {}: {}", task.id, exc
        )
        return False
    return True


def _as_utc(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _heartbeat_findings(now: datetime) -> list[str]:
    """What a check-in would be about: stalled sessions and long-unanswered blockers."""
    db = get_database()
    running = running_chat_ids()
    findings: list[str] = []
    for project in db.list_projects(include_archived=False):
        by_chat: dict[str, list[Any]] = {}
        for task in db.list_tasks(project_id=project.id):
            if task.chat_id:
                by_chat.setdefault(task.chat_id, []).append(task)
        for chat_id, tasks in by_chat.items():
            last_update = max(
                (_as_utc(task.updated_at) for task in tasks if task.updated_at),
                default=None,
            )
            for task in tasks:
                updated = _as_utc(task.updated_at)
                if (
                    _needs_attention(task)
                    and updated
                    and now - updated >= REMIND_BLOCKED_AFTER
                ):
                    findings.append(f"blocked:{task.id}:{task.waiting_reason}")
            stalled = (
                chat_id not in running
                and any(task.status in ("pending", "in_progress") for task in tasks)
                and not any(_needs_attention(task) for task in tasks)
                and last_update is not None
                and now - last_update >= STALL_AFTER
            )
            if stalled:
                findings.append(f"stalled:{chat_id}")
    return sorted(findings)


def should_run_focal_heartbeat(instructions: str) -> bool:
    """Decide in code whether a Focal check-in is worth a model turn.

    A checklist the user edited always runs, since only the model can judge
    their items. The built-in one runs only when there is something to raise
    that differs from the last check-in, so a quiet afternoon costs nothing.
    """
    built_in = {
        text.strip() for text in (DEFAULT_FOCAL_HEARTBEAT, *_PREVIOUS_FOCAL_HEARTBEATS)
    }
    if instructions.strip() not in built_in:
        return True
    findings = _heartbeat_findings(datetime.now(timezone.utc))
    if not findings:
        return False
    chat = get_database().get_chat(FOCAL_CHAT_ID)
    raised = (chat.config or {}).get("focal_heartbeat_signature") if chat else None
    return raised != _findings_signature(findings)


def _findings_signature(findings: list[str]) -> str:
    return hashlib.sha256("\n".join(findings).encode()).hexdigest()


def record_focal_heartbeat_done(chat_id: str) -> None:
    """Mark the current findings as raised once a Focal check-in has finished.

    Recorded only after the turn succeeds: a check-in that was never claimed,
    hit a busy chat or failed has not told the user anything, and marking it
    up front made every later check-in skip the same unchanged findings.
    """
    if not is_focal_chat_id(chat_id):
        return
    findings = _heartbeat_findings(datetime.now(timezone.utc))
    get_database().merge_chat_config(
        FOCAL_CHAT_ID, {"focal_heartbeat_signature": _findings_signature(findings)}
    )


def record_skipped_heartbeat() -> None:
    """Count a skipped check-in as run, so the schedule moves a full interval on."""
    get_database().merge_chat_config(
        FOCAL_CHAT_ID,
        {"heartbeat_last_run_at": datetime.now(timezone.utc).isoformat()},
    )


_MAX_REPLY_CHARS = 4000


def _focal_follows(chat: Optional[ChatModel]) -> bool:
    """Sessions the Focal Agent started, or has sent work to."""
    config = (chat.config or {}) if chat else {}
    return bool(
        config.get("parent_chat_id") == FOCAL_CHAT_ID or config.get("focal_watching")
    )


def watch_session(chat_id: str) -> None:
    """Remember that the Focal Agent sent this session work, so it hears when it ends."""
    get_database().merge_chat_config(chat_id, {"focal_watching": True})


def _focal_request_in_flight(chat_id: str) -> bool:
    """Whether a message from the Focal Agent to this session is still being handled.

    Its reply goes back to the Focal Agent anyway, so a separate notice would
    say the same thing twice.
    """
    return any(
        record.get("sender_chat_id") == FOCAL_CHAT_ID
        and record.get("status") in ("pending", "processing")
        for record in get_database().list_agent_messages(
            target_chat_id=chat_id, limit=20
        )
    )


def route_focal_reply(message: dict[str, Any], reply_text: str) -> bool:
    """Send a session's answer to a Focal Agent message back to the Focal Agent.

    Sub-agents already report to whoever messaged them; a project session did
    not, so when Focal asked one to do something, its report stayed in the
    session's own chat and Focal never heard it was done.
    """
    target_chat_id = str(message.get("target_chat_id") or "")
    if (
        message.get("kind", "agent_message") != "agent_message"
        or message.get("sender_chat_id") != FOCAL_CHAT_ID
        or target_chat_id == FOCAL_CHAT_ID
        or not reply_text.strip()
    ):
        return False
    db = get_database()
    chat = db.get_chat(target_chat_id)
    if chat is None:
        return False
    project = db.get_project(chat.project_id) if chat.project_id else None
    text = reply_text.strip()
    if len(text) > _MAX_REPLY_CHARS:
        text = text[:_MAX_REPLY_CHARS] + "\n[… truncated; use agent_read for the rest]"
    from suzent.core.agent_inbox import enqueue_agent_message

    try:
        enqueue_agent_message(
            target_chat_id=FOCAL_CHAT_ID,
            sender_chat_id=target_chat_id,
            content=(
                f"Reply from session {chat.title} (`{target_chat_id}`)"
                f" in project {project.name if project else 'unknown'}:\n\n{text}"
            ),
            kind="session_reply_notification",
            message_id=f"focal-reply-{message['message_id']}",
            payload={"in_reply_to": message["message_id"]},
        )
    except Exception as exc:
        logger.warning("Failed to route a session reply to the Focal Agent: {}", exc)
        return False
    return True


def notify_focal_of_finished_session(chat_id: str) -> bool:
    """Tell the Focal Agent a session it follows has no open tasks left."""
    db = get_database()
    chat = db.get_chat(chat_id)
    if not _focal_follows(chat) or _focal_request_in_flight(chat_id):
        return False
    project_id = chat.project_id
    if not project_id or db.list_tasks(project_id=project_id, chat_id=chat_id):
        return False
    done = db.list_tasks(project_id=project_id, chat_id=chat_id, status="completed")
    project = db.get_project(project_id)
    lines = [
        f"Session finished in project {project.name if project else project_id}.",
        f"Session: {chat.title} (`{chat_id}`)",
        *(
            f"- #{task.id} {task.title}: {task.result_summary or 'done'}"
            for task in done
        ),
    ]
    from suzent.core.agent_inbox import enqueue_agent_message

    get_or_create_focal_chat()
    try:
        enqueue_agent_message(
            target_chat_id=FOCAL_CHAT_ID,
            sender_chat_id=chat_id,
            content="\n".join(lines),
            kind="session_finished_notification",
            payload={"project_id": project_id},
        )
    except Exception as exc:
        logger.warning(
            "Failed to notify Focal Agent that {} finished: {}", chat_id, exc
        )
        return False
    return True


def announce_focal_reply(target_chat_id: str, text: str) -> None:
    """Surface what the Focal Agent said when an event woke it in the background.

    A woken turn lands in the Focal conversation, which the user may not have
    open, so anything it says is also queued as a desktop notification.
    """
    if target_chat_id != FOCAL_CHAT_ID or not text.strip():
        return
    try:
        get_database().create_background_notification(
            source="focal", title=FOCAL_TITLE, result=text.strip()
        )
    except Exception as exc:
        logger.warning("Failed to queue Focal Agent notification: {}", exc)


def focal_tools() -> list[dict[str, str]]:
    """The Focal Agent's fixed tools, for display."""
    from suzent.tools.registry import get_tool_summaries

    return get_tool_summaries(list(FOCAL_TOOL_NAMES))


def _focal_wakeup_jobs() -> list[Any]:
    from suzent.tools.schedule_tool import AGENT_SOURCE

    return [
        job
        for job in get_database().list_cron_jobs_for_chat(
            FOCAL_CHAT_ID, active_only=True
        )
        if job.source == AGENT_SOURCE
    ]


def focal_wakeups() -> list[dict[str, Any]]:
    """Wake-ups the Focal Agent scheduled for itself, soonest first."""
    from suzent.tools.schedule_tool import ScheduleTool

    jobs = sorted(
        _focal_wakeup_jobs(),
        key=lambda job: job.next_run_at or datetime.max,
    )
    return [
        {
            "id": job.id,
            "name": job.name,
            "kind": "check" if job.suppress_ok else "reminder",
            "schedule": ScheduleTool._describe(job),
            "scheduleKind": job.schedule_kind or "cron",
            "nextRunAt": job.next_run_at.isoformat() if job.next_run_at else None,
            "lastError": job.last_error,
        }
        for job in jobs
    ]


def cancel_focal_wakeup(job_id: int) -> bool:
    """Cancel one of the Focal Agent's own wake-ups; anything else is refused."""
    if job_id not in {job.id for job in _focal_wakeup_jobs()}:
        return False
    get_database().delete_cron_job(job_id)
    return True
