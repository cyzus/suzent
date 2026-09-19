"""
Scheduler Brain: the one timing loop behind every scheduled task.

A task is a row in ``cron_jobs``. ``schedule_kind`` decides when it fires
(cron expression, fixed interval, or a single ``run_at``), and ``context_mode``
decides where the turn runs: an isolated ``cron-{id}`` chat, or bound to an
existing conversation so the task can see it.

Heartbeats are ordinary rows here too -- interval-scheduled, bound, with
``suppress_ok`` so a turn that finds nothing to report is rolled back. The
HeartbeatRunner still owns heartbeat *execution*; this module owns the clock.
"""

import asyncio
import random
import dateutil.parser
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Set

from croniter import croniter

from suzent.config import CONFIG
from suzent.core.base_brain import BaseBrain, get_active
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.core.stream_registry import (
    stream_controls,
    producing_run,
    register_background_stream,
    unregister_background_stream,
)

logger = get_logger(__name__)


def build_cron_reminder(
    job_name: str,
    prompt: str,
    *,
    triggered_at: Optional[datetime] = None,
    last_run_at: Optional[datetime] = None,
) -> str:
    """Build the time-aware reminder delivered to a scheduled agent turn."""
    local_now = triggered_at or datetime.now().astimezone()
    if local_now.tzinfo is None:
        local_now = local_now.astimezone()

    timezone_name = local_now.tzname() or "local time"
    utc_offset = local_now.strftime("%z")
    formatted_offset = (
        f"UTC{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else "UTC offset unknown"
    )
    current_time = local_now.isoformat(timespec="seconds")
    if last_run_at is None:
        last_run = "none (first run)"
    else:
        local_last_run = (
            last_run_at if last_run_at.tzinfo is not None else last_run_at.astimezone()
        )
        last_run = local_last_run.isoformat(timespec="seconds")

    return (
        f"**Scheduled Task: {job_name}**\n\n"
        "You were automatically woken by the cron scheduler.\n"
        f"Current local time: {current_time} ({timezone_name}, {formatted_offset})\n\n"
        f"Last run: {last_run}\n\n"
        f"{prompt}"
    )


def build_bound_task_reminder(
    job_name: str,
    prompt: str,
    *,
    triggered_at: Optional[datetime] = None,
    last_run_at: Optional[datetime] = None,
) -> str:
    """Reminder for a task firing inside an existing conversation.

    The isolated-chat wording ("you were woken by the scheduler") would be
    confusing mid-conversation, so a bound task says plainly that it is a
    scheduled interruption and that the surrounding chat is its context.
    """
    body = build_cron_reminder(
        job_name, prompt, triggered_at=triggered_at, last_run_at=last_run_at
    )
    return body.replace(
        "You were automatically woken by the cron scheduler.",
        "A scheduled task attached to this conversation just fired. "
        "The conversation above is your context; continue it rather than "
        "starting over, and stay silent unless there is something worth saying.",
        1,
    )


def _resolve_timezone(name: Optional[str]):
    """Return a tzinfo for an IANA name, or None to use machine local time."""
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception as exc:
        logger.warning(f"Unknown timezone {name!r}, falling back to local time: {exc}")
        return None


def compute_next_run(job, *, after: Optional[datetime] = None) -> Optional[datetime]:
    """Next fire time for a task as naive local time.

    Returns None when the task has nothing left to schedule -- a one-shot that
    already ran, or a row whose schedule fields are incomplete.

    Cron expressions are evaluated in the task's own timezone and then
    converted back to local naive time, so every stored timestamp and every
    comparison in the tick loop stays in a single frame of reference.
    """
    base = after or datetime.now()
    kind = job.schedule_kind or "cron"

    if kind == "once":
        # A one-shot fires exactly once; last_run_at marks it spent.
        if job.last_run_at:
            return None
        return job.run_at

    if kind == "interval":
        minutes = job.interval_minutes or 0
        if minutes < 1:
            return None
        nxt = base + timedelta(minutes=minutes)
    else:
        if not job.cron_expr:
            return None
        tz = _resolve_timezone(job.timezone)
        local_base = base.astimezone(tz) if tz else base
        nxt = croniter(job.cron_expr, local_base).get_next(datetime)
        if nxt.tzinfo is not None:
            nxt = nxt.astimezone().replace(tzinfo=None)

    if job.jitter_seconds:
        nxt = nxt + timedelta(seconds=random.uniform(0, job.jitter_seconds))
    return nxt


def schedule_period_seconds(job) -> Optional[float]:
    """Nominal gap between two fires, or None when there isn't a repeating one."""
    kind = job.schedule_kind or "cron"
    if kind == "interval":
        return ((job.interval_minutes or 0) * 60) or None
    if kind == "cron" and job.cron_expr:
        try:
            iterator = croniter(job.cron_expr, datetime.now())
            first = iterator.get_next(datetime)
            second = iterator.get_next(datetime)
            return (second - first).total_seconds()
        except Exception:
            return None
    return None


def is_missed_run(job, now: datetime) -> bool:
    """Whether a due run is stale enough to skip under the catch-up policy.

    After the machine sleeps, every overdue task would otherwise fire at once.
    A run overdue by more than one full period is treated as missed; with
    ``catch_up="run_once"`` it still runs, once, instead of being dropped.
    One-shots are never skipped -- a reminder that fires late is still useful.
    """
    if (job.catch_up or "skip") != "skip":
        return False
    if (job.schedule_kind or "cron") == "once":
        return False
    if not job.next_run_at:
        return False
    period = schedule_period_seconds(job)
    if not period:
        return False
    return (now - job.next_run_at).total_seconds() > period


HEARTBEAT_SOURCE = "heartbeat"


def _parse_heartbeat_last_run(cfg: dict) -> Optional[datetime]:
    """chat.config stores a UTC ISO string; the scheduler works in local naive."""
    raw = cfg.get("heartbeat_last_run_at")
    if not raw:
        return None
    try:
        parsed = dateutil.parser.isoparse(raw)
    except Exception:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _heartbeat_next_run(cfg: dict, interval_minutes: int) -> datetime:
    """When a chat's heartbeat is next owed. A chat that never ran one is due now."""
    last = _parse_heartbeat_last_run(cfg)
    base = last or (datetime.now() - timedelta(minutes=interval_minutes))
    return base + timedelta(minutes=interval_minutes)


def sync_heartbeat_tasks(db) -> None:
    """Project heartbeat-enabled chats onto scheduled-task rows.

    Heartbeat stays configured where the UI already writes it -- ``chat.config``
    plus the project's ``heartbeat.md`` -- while the scheduler owns its clock.
    This reconciles the two in both directions: a config change re-arms the row,
    and a heartbeat the frontend ran itself pushes the row's next fire time out
    so the scheduler doesn't immediately run a second one behind it.
    """
    enabled_chats = {chat.id: chat for chat in db.get_active_heartbeats()}

    for chat_id, chat in enabled_chats.items():
        cfg = chat.config or {}
        try:
            interval = max(1, int(cfg.get("heartbeat_interval_minutes", 30)))
        except (TypeError, ValueError):
            interval = 30

        row = db.find_cron_job_by_source(HEARTBEAT_SOURCE, chat_id)
        if row is None:
            job_id = db.create_cron_job(
                name=f"Heartbeat: {chat.title or chat_id[:8]}",
                prompt="",
                delivery_mode="none",
                schedule_kind="interval",
                interval_minutes=interval,
                chat_id=chat_id,
                context_mode="bound",
                suppress_ok=True,
                source=HEARTBEAT_SOURCE,
            )
            db.update_cron_job_run_state(
                job_id, next_run_at=_heartbeat_next_run(cfg, interval)
            )
            continue

        patch = {}
        if not row.active:
            patch["active"] = True
        if row.interval_minutes != interval:
            patch["interval_minutes"] = interval
        if patch:
            db.update_cron_job(row.id, **patch)

        external = _parse_heartbeat_last_run(cfg)
        if external is not None and (
            row.last_run_at is None or external > row.last_run_at
        ):
            db.update_cron_job_run_state(
                row.id,
                last_run_at=external,
                next_run_at=external + timedelta(minutes=interval),
            )
        elif "interval_minutes" in patch or not row.next_run_at:
            db.update_cron_job_run_state(
                row.id, next_run_at=_heartbeat_next_run(cfg, interval)
            )

    # Rows whose chat turned heartbeat off (or vanished) go dormant.
    for row in db.list_cron_jobs(active_only=True):
        if row.source == HEARTBEAT_SOURCE and row.chat_id not in enabled_chats:
            db.update_cron_job(row.id, active=False)


def get_active_scheduler() -> Optional["SchedulerBrain"]:
    """Return the active SchedulerBrain instance, or None if not running."""
    return get_active(SchedulerBrain)


def ensure_cron_presets(db, activate_existing: bool = False) -> dict:
    """Idempotently create or update cron jobs declared in CONFIG.cron_presets.

    Each preset spec supports:
      name          (str, required)  — unique job name
      cron_expr     (str, required)  — standard cron expression
      prompt        (str, required)  — message sent to the agent
      delivery_mode (str)            — "announce" | "silent" (default: "silent")
      model_override (str|None)      — optional model override
      enabled       (bool)           — hard-disable this preset (default: True)
      requires      (str)            — CONFIG field name that must be truthy
    """
    presets = getattr(CONFIG, "cron_presets", [])
    if not presets:
        return {
            "success": True,
            "created": [],
            "updated": [],
            "unchanged": [],
            "skipped": [],
        }

    jobs_by_name = {job.name: job for job in db.list_cron_jobs()}
    now = datetime.now()
    created, updated, unchanged, skipped = [], [], [], []

    for spec in presets:
        name = spec.get("name")
        if not name:
            continue

        # Per-preset enabled flag
        if not spec.get("enabled", True):
            skipped.append(name)
            continue

        # Feature-flag guard: skip if a required config field is falsy
        requires = spec.get("requires")
        if requires and not getattr(CONFIG, requires, False):
            skipped.append(name)
            continue

        cron_expr = spec.get("cron_expr")
        prompt = spec.get("prompt", "")
        delivery_mode = spec.get("delivery_mode", "silent")
        model_override = spec.get("model_override") or None

        if not cron_expr:
            logger.warning(f"Cron preset '{name}' has no cron_expr, skipping")
            skipped.append(name)
            continue

        desired = {
            "cron_expr": cron_expr,
            "prompt": prompt,
            "delivery_mode": delivery_mode,
            "model_override": model_override,
        }

        existing = jobs_by_name.get(name)
        if not existing:
            job_id = db.create_cron_job(
                name=name,
                cron_expr=cron_expr,
                prompt=prompt,
                active=True,
                delivery_mode=delivery_mode,
                model_override=model_override,
            )
            next_run = croniter(cron_expr, now).get_next(datetime)
            db.update_cron_job_run_state(job_id, next_run_at=next_run)
            created.append(name)
            continue

        patch = {k: v for k, v in desired.items() if getattr(existing, k) != v}
        if activate_existing and not existing.active:
            patch["active"] = True

        if patch:
            db.update_cron_job(existing.id, **patch)
            active_after = patch.get("active", existing.active)
            cron_expr_after = patch.get("cron_expr", existing.cron_expr)
            if active_after and ("cron_expr" in patch or not existing.next_run_at):
                next_run = croniter(cron_expr_after, now).get_next(datetime)
                db.update_cron_job_run_state(existing.id, next_run_at=next_run)
            updated.append(name)
        else:
            unchanged.append(name)

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
    }


# Shim for any callers that still reference the old name.
def ensure_wiki_cron_presets(db, activate_existing: bool = False) -> dict:
    return ensure_cron_presets(db, activate_existing=activate_existing)


class SchedulerBrain(BaseBrain):
    """
    Periodically checks cron jobs and executes them via ChatProcessor.
    Routes announce notifications to an in-memory deque for frontend polling.
    """

    _brain_name = "SchedulerBrain"

    def __init__(self, tick_interval: float = 30.0):
        super().__init__()
        self.tick_interval = tick_interval
        self._pending_notifications: deque = deque(maxlen=20)
        # Job ids with a run in progress. A tick must not fire a task that is
        # already running -- for a bound task the chat's stream guard would
        # catch it, but a one-shot disarms itself and has no other interlock.
        self._in_flight: Set[int] = set()

    async def start(self):
        """Start the scheduler loop."""
        await super().start()

        try:
            db = get_database()
            preset_result = ensure_cron_presets(db)
            if preset_result.get("success"):
                logger.info(
                    "Cron presets ensured: "
                    f"created={len(preset_result['created'])}, "
                    f"updated={len(preset_result['updated'])}, "
                    f"unchanged={len(preset_result['unchanged'])}, "
                    f"skipped={len(preset_result['skipped'])}"
                )
        except Exception as e:
            logger.error(f"Failed to ensure cron presets: {e}")

        self._initialize_schedules()

    async def trigger_job_now(self, job_id: int):
        """Manually trigger a job for immediate execution."""
        if job_id in self._in_flight:
            logger.info(f"Scheduled task {job_id} is already running, not re-firing")
            return
        asyncio.create_task(self._execute_job(job_id))

    def drain_notifications(self) -> list:
        """Drain durable notifications, with the in-memory queue as fallback."""
        notifications = []
        try:
            persisted = get_database().drain_background_notifications()
            notifications.extend(
                {
                    "id": item.id,
                    "job_id": item.job_id,
                    "job_name": item.title,
                    "result": item.result,
                    "source": item.source,
                    "timestamp": item.created_at.isoformat(),
                }
                for item in persisted
            )
        except Exception as exc:
            logger.warning(f"Failed to drain durable notifications: {exc}")
        notifications.extend(self._pending_notifications)
        self._pending_notifications.clear()
        return notifications

    def add_notification(self, source: str, result: str) -> None:
        """Persist a notification from a non-cron source (e.g. goal mode)."""
        try:
            get_database().create_background_notification(
                source=source, title=source, result=result
            )
        except Exception as exc:
            logger.warning(f"Failed to persist background notification: {exc}")
            self._pending_notifications.append(
                {
                    "job_id": None,
                    "job_name": source,
                    "result": result[:500],
                    "timestamp": datetime.now().isoformat(),
                }
            )

    # -- Internal ------------------------------------------------------------

    def _initialize_schedules(self):
        """Compute initial next_run_at for active tasks missing one."""
        try:
            db = get_database()
            for job in db.list_cron_jobs(active_only=True):
                if not job.next_run_at:
                    self._arm(db, job)
        except Exception as e:
            logger.error(f"Failed to initialize scheduled task timings: {e}")

    def _arm(self, db, job, *, after: Optional[datetime] = None) -> None:
        """Set a task's next fire time, deactivating it when it has none left."""
        try:
            nxt = compute_next_run(job, after=after)
        except Exception as e:
            logger.error(f"Invalid schedule for task {job.id}: {e}")
            db.update_cron_job_run_state(job.id, last_error=str(e), clear_next_run=True)
            db.update_cron_job(job.id, active=False)
            return

        if nxt is None:
            db.update_cron_job_run_state(job.id, clear_next_run=True)
            db.update_cron_job(job.id, active=False)
            logger.info(f"Scheduled task {job.id} has no further runs, deactivated")
            return

        db.update_cron_job_run_state(job.id, next_run_at=nxt)

    async def _run_loop(self):
        """Main tick loop -- checks due jobs every tick_interval seconds."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler tick: {e}")

            try:
                await asyncio.sleep(self.tick_interval)
            except asyncio.CancelledError:
                break

    async def _tick(self):
        """Single tick: reconcile heartbeat rows, then fire whatever is due."""
        db = get_database()
        now = datetime.now()

        try:
            sync_heartbeat_tasks(db)
        except Exception as e:
            logger.error(f"Failed to sync heartbeat tasks: {e}")

        for job in db.list_cron_jobs(active_only=True):
            if job.id in self._in_flight:
                continue

            if not job.next_run_at:
                self._arm(db, job, after=now)
                continue

            if job.next_run_at > now:
                continue

            if is_missed_run(job, now):
                logger.info(
                    f"Skipping missed run of scheduled task {job.id} "
                    f"(due {job.next_run_at.isoformat()}, catch_up=skip)"
                )
                self._arm(db, job, after=now)
                continue

            asyncio.create_task(self._execute_job(job.id))

    async def _execute_job(self, job_id: int):
        """Execute a single scheduled task."""
        db = get_database()
        job = db.get_cron_job(job_id)
        if not job or not job.active:
            return

        bound = (job.context_mode or "isolated") == "bound" and bool(job.chat_id)
        chat_id = job.chat_id if bound else f"cron-{job_id}"

        if chat_id in stream_controls:
            if bound:
                # The chat this task rides on is mid-turn. Competing with the
                # user is the normal case for a bound task, not a failure, so
                # slide to the next tick rather than spending a retry -- five
                # retries would otherwise deactivate the task during a
                # conversation.
                self._defer_bound_job(db, job)
                return

            error = "Previous cron run is still active"
            logger.warning(f"Deferring cron job {job_id} -- {error.lower()}")
            now = datetime.now()
            run_id = db.create_cron_run(job_id, now)
            db.finish_cron_run(run_id, "error", error=error)
            self._handle_retry(db, job_id, job.retry_count or 0, now, error)
            return

        if job.source == HEARTBEAT_SOURCE:
            self._dispatch_heartbeat(db, job)
            return

        self._in_flight.add(job_id)
        try:
            await self._run_scheduled_task(db, job, chat_id, bound=bound)
        finally:
            self._in_flight.discard(job_id)

    def _defer_bound_job(self, db, job) -> None:
        """Slide a bound task past a busy chat without spending a retry."""
        retry_at = datetime.now() + timedelta(seconds=max(self.tick_interval, 30.0))
        db.update_cron_job_run_state(job.id, next_run_at=retry_at)
        logger.debug(f"Chat {job.chat_id} is busy, deferring scheduled task {job.id}")

    def _dispatch_heartbeat(self, db, job) -> None:
        """Hand a due heartbeat to the runner and re-arm the row.

        Heartbeats keep their own delivery path: the runner marks the chat
        pending so an attached frontend can claim and stream the turn, and only
        runs it server-side if nobody does. They produce no run history and no
        notification, so they never reach the generic task path below.
        """
        from suzent.core.heartbeat import get_active_heartbeat

        now = datetime.now()
        runner = get_active_heartbeat()
        if runner is None or not runner.enabled:
            # Subsystem is off; keep the row moving so it doesn't pile up.
            self._arm(db, job, after=now)
            return

        db.update_cron_job_run_state(
            job.id,
            last_run_at=now,
            next_run_at=now + timedelta(minutes=job.interval_minutes or 30),
            retry_count=0,
        )
        runner.mark_heartbeat_pending(job.chat_id)

    async def _run_scheduled_task(self, db, job, chat_id: str, *, bound: bool):
        """Advance the schedule, run the turn, and record the outcome."""
        job_id = job.id
        one_shot = (job.schedule_kind or "cron") == "once"
        # Preserve the previous value before advancing the schedule for this run.
        last_run_at = job.last_run_at
        now = datetime.now()

        # Advance before execution so a slow turn cannot drift the next fire
        # time. A one-shot disarms instead -- it must not fire twice.
        if one_shot:
            db.update_cron_job_run_state(
                job_id, last_run_at=now, retry_count=0, clear_next_run=True
            )
        else:
            try:
                nxt = compute_next_run(job, after=now)
            except Exception as e:
                logger.error(f"Invalid schedule for task {job_id}: {e}")
                db.update_cron_job_run_state(
                    job_id, last_error=str(e), clear_next_run=True
                )
                db.update_cron_job(job_id, active=False)
                return
            db.update_cron_job_run_state(
                job_id,
                last_run_at=now,
                next_run_at=nxt,
                retry_count=0,
                clear_next_run=nxt is None,
            )

        if not bound:
            self._ensure_cron_chat(chat_id, job)
        run_id = db.create_cron_run(job_id, now)

        try:
            if bound:
                response_text = await self._run_bound_turn(
                    chat_id, job, last_run_at=last_run_at
                )
            else:
                response_text = await self._run_chat_turn(
                    chat_id, job, db, job_id, run_id, last_run_at=last_run_at
                )

            db.update_cron_job_run_state(
                job_id, last_result=response_text, clear_error=True
            )
            db.finish_cron_run(run_id, "success", result=response_text)
            # A suppressed bound turn left no trace in the chat, so it must not
            # light up the unread badge either.
            if response_text or not bound:
                db.set_last_result_at(chat_id)

            if one_shot:
                db.update_cron_job(job_id, active=False)
                logger.info(f"One-shot task {job_id} completed, deactivated")

            if job.delivery_mode == "announce" and response_text:
                try:
                    db.create_background_notification(
                        source="cron",
                        title=job.name,
                        result=response_text,
                        job_id=job.id,
                    )
                except Exception as exc:
                    logger.warning(f"Failed to persist cron notification: {exc}")
                    self._pending_notifications.append(
                        {
                            "job_id": job.id,
                            "job_name": job.name,
                            "result": response_text[:500],
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

        except Exception as e:
            logger.error(f"Scheduled task {job_id} execution failed: {e}")
            db.finish_cron_run(run_id, "error", error=str(e))
            self._handle_retry(db, job_id, job.retry_count or 0, now, str(e))

    async def _run_bound_turn(
        self, chat_id: str, job, *, last_run_at: Optional[datetime] = None
    ) -> str:
        """Run a task turn inside the chat it is bound to.

        Bound turns reuse the HeartbeatRunner's executor: it already knows how
        to take a background turn in a live conversation, recognise an answer
        that reports nothing, and roll those messages back out of the
        transcript so a quiet check leaves the chat untouched.
        """
        from suzent.core.heartbeat import get_active_heartbeat

        runner = get_active_heartbeat()
        if runner is None:
            raise RuntimeError(
                "HeartbeatRunner is not running; cannot run a chat-bound task"
            )

        reminder = build_bound_task_reminder(
            job.name, job.prompt, last_run_at=last_run_at
        )
        return await runner.run_bound_turn(
            chat_id,
            reminder,
            suppress_ok=bool(job.suppress_ok),
            model_override=job.model_override,
        )

    async def _run_chat_turn(
        self,
        chat_id: str,
        job,
        db,
        job_id: int,
        run_id: int,
        *,
        last_run_at: Optional[datetime] = None,
    ) -> str:
        """Run a ChatProcessor turn for a cron job and return the response."""
        from suzent.core.chat_processor import ChatProcessor

        cron_msg = build_cron_reminder(job.name, job.prompt, last_run_at=last_run_at)

        processor = ChatProcessor()
        config_override = self._build_config_override(
            db, model_override=job.model_override
        )

        stream_queue = register_background_stream(chat_id)
        try:
            # The frontend can attach to this queue and stop the job by name,
            # so the turn's control has to know which run it is cancelling.
            with producing_run(stream_queue.replay):
                return await processor.process_turn_text(
                    chat_id=chat_id,
                    user_id=CONFIG.user_id,
                    message_content="",
                    config_override=config_override,
                    _stream_queue=stream_queue,
                    system_reminders=[cron_msg],
                )
        except RuntimeError as e:
            logger.error(f"Cron job {job_id} error: {e}")
            db.update_cron_job_run_state(job_id, last_error=str(e))
            raise
        finally:
            unregister_background_stream(chat_id, stream_queue)

    def _build_config_override(
        self, db, *, model_override: Optional[str] = None
    ) -> dict:
        """Build config override dict, resolving model from override or user prefs."""
        from suzent.agent_manager import build_agent_config

        base_config: dict = {
            "memory_enabled": True,
            "permission_mode": "auto",
            "interaction_profile": "headless",
        }
        if model_override:
            base_config["model"] = model_override

        return build_agent_config(base_config, require_social_tool=True)

    def _handle_retry(
        self, db, job_id: int, current_retry: int, now: datetime, error: str
    ):
        """Apply exponential backoff retry or deactivate after max retries."""
        max_retries = 5
        if current_retry < max_retries:
            backoff = timedelta(minutes=2**current_retry)
            db.update_cron_job_run_state(
                job_id,
                last_error=error,
                next_run_at=now + backoff,
                retry_count=current_retry + 1,
            )
        else:
            db.update_cron_job_run_state(
                job_id, last_error=f"Max retries exceeded: {error}"
            )
            db.update_cron_job(job_id, active=False)
            logger.warning(
                f"Cron job {job_id} deactivated after {current_retry} retries"
            )

    def _ensure_cron_chat(self, chat_id: str, job):
        """Ensure a chat record exists for this cron job."""
        db = get_database()
        if not db.get_chat(chat_id):
            db.create_chat(
                title=f"Cron: {job.name}",
                config={"platform": "cron", "cron_job_id": job.id},
                chat_id=chat_id,
            )
