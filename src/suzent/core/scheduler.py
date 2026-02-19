"""
Scheduler Brain: Crontab-based automated task execution.

Module-level singleton with an asyncio task loop that fires jobs
via ChatProcessor on their cron schedule.
"""

import asyncio
import json
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from croniter import croniter

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.streaming import stream_controls

logger = get_logger(__name__)

_active_instance: Optional["SchedulerBrain"] = None


def get_active_scheduler() -> Optional["SchedulerBrain"]:
    """Return the active SchedulerBrain instance, or None if not running."""
    return _active_instance


class SchedulerBrain:
    """
    Periodically checks cron jobs and executes them via ChatProcessor.
    Routes announce notifications to an in-memory deque for frontend polling.
    """

    def __init__(self, tick_interval: float = 30.0):
        self.tick_interval = tick_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._pending_notifications: deque = deque(maxlen=20)

    async def start(self):
        """Start the scheduler loop."""
        global _active_instance
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        _active_instance = self

        self._initialize_schedules()
        logger.info("SchedulerBrain started.")

    async def stop(self):
        """Stop the scheduler loop."""
        global _active_instance
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _active_instance = None
        logger.info("SchedulerBrain stopped.")

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

        processor = ChatProcessor()
        config_override = self._build_config_override(
            db, model_override=job.model_override
        )

        full_response = ""
        async for chunk in processor.process_turn(
            chat_id=chat_id,
            user_id=CONFIG.user_id,
            message_content=job.prompt,
            config_override=config_override,
        ):
            if not chunk.startswith("data: "):
                continue
            try:
                data = json.loads(chunk[6:].strip())
                evt = data.get("type")
                content = data.get("data")

                if evt == "final_answer":
                    full_response = content
                elif evt == "error":
                    logger.error(f"Cron job {job_id} error: {content}")
                    db.update_cron_job_run_state(job_id, last_error=str(content))
                    db.finish_cron_run(run_id, "error", error=str(content))
                    return ""
            except json.JSONDecodeError:
                pass

        return full_response.strip()

    def _build_config_override(
        self, db, *, model_override: Optional[str] = None
    ) -> dict:
        """Build config override dict, resolving model from override or user prefs."""
        config: dict = {"memory_enabled": True}

        model_id = model_override
        if not model_id:
            try:
                if prefs := db.get_user_preferences():
                    model_id = prefs.model
            except Exception as e:
                logger.warning(f"Failed to load user preferences: {e}")

        if model_id:
            config["model"] = model_id

        return config

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
