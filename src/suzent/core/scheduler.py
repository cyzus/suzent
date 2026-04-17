"""
Scheduler Brain: Crontab-based automated task execution.

Module-level singleton with an asyncio task loop that fires jobs
via ChatProcessor on their cron schedule.
"""

import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from croniter import croniter

from suzent.config import CONFIG
from suzent.core.base_brain import BaseBrain, get_active
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.core.stream_registry import (
    stream_controls,
    register_background_stream,
    unregister_background_stream,
)

logger = get_logger(__name__)


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
        asyncio.create_task(self._execute_job(job_id))

    def drain_notifications(self) -> list:
        """Drain and return all pending notifications."""
        notifications = list(self._pending_notifications)
        self._pending_notifications.clear()
        return notifications

    # -- Internal ------------------------------------------------------------

    def _initialize_schedules(self):
        """Compute initial next_run_at for active jobs missing one."""
        try:
            db = get_database()
            now = datetime.now()
            for job in db.list_cron_jobs(active_only=True):
                if not job.next_run_at:
                    nxt = croniter(job.cron_expr, now).get_next(datetime)
                    db.update_cron_job_run_state(job.id, next_run_at=nxt)
        except Exception as e:
            logger.error(f"Failed to initialize cron job schedules: {e}")

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
        """Single tick: find due jobs and fire them."""
        db = get_database()
        now = datetime.now()

        for job in db.list_cron_jobs(active_only=True):
            if not job.next_run_at:
                nxt = croniter(job.cron_expr, now).get_next(datetime)
                db.update_cron_job_run_state(job.id, next_run_at=nxt)
                continue

            if job.next_run_at <= now:
                asyncio.create_task(self._execute_job(job.id))

    async def _execute_job(self, job_id: int):
        """Execute a single cron job."""
        db = get_database()
        job = db.get_cron_job(job_id)
        if not job or not job.active:
            return

        chat_id = f"cron-{job_id}"

        if chat_id in stream_controls:
            logger.debug(f"Skipping cron job {job_id} -- stream already active")
            return

        # Advance schedule before execution to avoid drift
        now = datetime.now()
        try:
            nxt = croniter(job.cron_expr, now).get_next(datetime)
            db.update_cron_job_run_state(
                job_id, last_run_at=now, next_run_at=nxt, retry_count=0
            )
        except Exception as e:
            logger.error(f"Invalid cron expression for job {job_id}: {e}")
            db.update_cron_job_run_state(job_id, last_error=str(e), next_run_at=None)
            db.update_cron_job(job_id, active=False)
            return

        self._ensure_cron_chat(chat_id, job)
        run_id = db.create_cron_run(job_id, now)

        try:
            response_text = await self._run_chat_turn(chat_id, job, db, job_id, run_id)

            db.update_cron_job_run_state(job_id, last_result=response_text)
            db.finish_cron_run(run_id, "success", result=response_text)
            db.set_last_result_at(chat_id)

            if job.delivery_mode == "announce" and response_text:
                self._pending_notifications.append(
                    {
                        "job_id": job.id,
                        "job_name": job.name,
                        "result": response_text[:500],
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        except Exception as e:
            logger.error(f"Cron job {job_id} execution failed: {e}")
            db.finish_cron_run(run_id, "error", error=str(e))
            self._handle_retry(db, job_id, job.retry_count or 0, now, str(e))

    async def _run_chat_turn(
        self, chat_id: str, job, db, job_id: int, run_id: int
    ) -> str:
        """Run a ChatProcessor turn for a cron job and return the response."""
        from suzent.core.chat_processor import ChatProcessor

        cron_msg = f"**Scheduled Task: {job.name}**\n\n{job.prompt}"

        processor = ChatProcessor()
        config_override = self._build_config_override(
            db, model_override=job.model_override
        )

        stream_queue = register_background_stream(chat_id)
        try:
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
            db.finish_cron_run(run_id, "error", error=str(e))
            return ""
        finally:
            unregister_background_stream(chat_id)

    def _build_config_override(
        self, db, *, model_override: Optional[str] = None
    ) -> dict:
        """Build config override dict, resolving model from override or user prefs."""
        from suzent.agent_manager import build_agent_config

        base_config: dict = {"memory_enabled": True, "auto_approve_tools": True}
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
