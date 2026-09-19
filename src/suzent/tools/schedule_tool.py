"""Agent-facing scheduling: let a turn arrange its own future turns.

Cron jobs and heartbeats are configured by a human through the UI. This tool
gives the agent the same table, scoped to the conversation it is in, so it can
say "check back on this in twenty minutes" and actually mean it.

The guardrails below matter more than the surface area: a task the agent
schedules wakes the agent, which can schedule another one. Bounds on how many
tasks a chat may carry and how often they may fire keep that from turning into
a loop that quietly burns tokens while nobody is watching.
"""

from datetime import datetime, timedelta
from typing import Annotated, Optional

from croniter import croniter
from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.core.scheduler import compute_next_run
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)

AGENT_SOURCE = "agent"

# A chat may carry this many agent-scheduled tasks at once. Past it, the agent
# has to cancel something before it can add more.
MAX_AGENT_TASKS_PER_CHAT = 5

# Floors on how eagerly the agent may wake itself.
MIN_INTERVAL_MINUTES = 5
MIN_DELAY_MINUTES = 1

# A cron expression that fires more often than this is rejected, since a cron
# spec can be far tighter than the interval floor allows.
MIN_CRON_PERIOD_SECONDS = MIN_INTERVAL_MINUTES * 60


class ScheduleTool(Tool):
    """Schedule a future turn in this conversation, or manage ones already set."""

    name: str = "ScheduleTool"
    tool_name: str = "schedule_task"
    group: ToolGroup = ToolGroup.TASKS

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        action: Annotated[
            str,
            Field(
                description=(
                    "'create' a task, 'list' this chat's tasks, 'update' one, "
                    "or 'cancel' one."
                )
            ),
        ] = "list",
        name: Annotated[
            Optional[str],
            Field(description="Short label for the task, e.g. 'recheck CI'."),
        ] = None,
        prompt: Annotated[
            Optional[str],
            Field(
                description=(
                    "What you should do when it fires. Write it for your future "
                    "self: state the goal and how to tell you are done."
                )
            ),
        ] = None,
        in_minutes: Annotated[
            Optional[int],
            Field(description="Run once, this many minutes from now."),
        ] = None,
        at: Annotated[
            Optional[str],
            Field(description="Run once, at this ISO 8601 local timestamp."),
        ] = None,
        every_minutes: Annotated[
            Optional[int],
            Field(description=f"Repeat every N minutes (min {MIN_INTERVAL_MINUTES})."),
        ] = None,
        cron: Annotated[
            Optional[str],
            Field(description="Repeat on a 5-field cron expression."),
        ] = None,
        timezone: Annotated[
            Optional[str],
            Field(
                description="IANA timezone for a cron schedule, e.g. 'Asia/Shanghai'."
            ),
        ] = None,
        bind_to_chat: Annotated[
            bool,
            Field(
                description=(
                    "True (default) runs the task inside this conversation, so it "
                    "sees the history. False runs it in a fresh isolated chat, "
                    "which is cheaper and better for self-contained checks."
                )
            ),
        ] = True,
        quiet_if_nothing_to_report: Annotated[
            bool,
            Field(
                description=(
                    "For a bound task: if the turn finds nothing worth saying, "
                    "roll it back so the conversation is left untouched."
                )
            ),
        ] = True,
        task_id: Annotated[
            Optional[int],
            Field(description="Task to act on, for 'update' and 'cancel'."),
        ] = None,
    ) -> ToolResult:
        chat_id = ctx.deps.chat_id
        if not chat_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Scheduling needs a chat to attach to, and this turn has none.",
            )

        action = (action or "list").strip().lower()
        if action == "list":
            return self._list(chat_id)
        if action == "cancel":
            return self._cancel(chat_id, task_id)
        if action == "update":
            return self._update(chat_id, task_id, every_minutes, cron, prompt, name)
        if action == "create":
            return self._create(
                chat_id=chat_id,
                name=name,
                prompt=prompt,
                in_minutes=in_minutes,
                at=at,
                every_minutes=every_minutes,
                cron=cron,
                timezone=timezone,
                bind_to_chat=bind_to_chat,
                quiet_if_nothing_to_report=quiet_if_nothing_to_report,
            )
        return ToolResult.error_result(
            ToolErrorCode.INVALID_ARGUMENT,
            f"Unknown action {action!r}. Use create, list, update or cancel.",
        )

    # -- actions -------------------------------------------------------------

    def _create(
        self,
        *,
        chat_id: str,
        name: Optional[str],
        prompt: Optional[str],
        in_minutes: Optional[int],
        at: Optional[str],
        every_minutes: Optional[int],
        cron: Optional[str],
        timezone: Optional[str],
        bind_to_chat: bool,
        quiet_if_nothing_to_report: bool,
    ) -> ToolResult:
        if not prompt or not prompt.strip():
            return ToolResult.error_result(
                ToolErrorCode.MISSING_REQUIRED_PARAM,
                "prompt is required: say what the scheduled turn should do.",
            )

        given = [s for s in (in_minutes, at, every_minutes, cron) if s is not None]
        if len(given) != 1:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Give exactly one schedule: in_minutes, at, every_minutes or cron.",
            )

        db = get_database()
        existing = [
            job
            for job in db.list_cron_jobs_for_chat(chat_id, active_only=True)
            if job.source == AGENT_SOURCE
        ]
        if len(existing) >= MAX_AGENT_TASKS_PER_CHAT:
            names = ", ".join(f"#{j.id} {j.name}" for j in existing)
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                f"This chat already has {len(existing)} scheduled tasks "
                f"({names}). Cancel one before adding another.",
            )

        spec, error = self._resolve_schedule(
            in_minutes=in_minutes,
            at=at,
            every_minutes=every_minutes,
            cron=cron,
        )
        if error:
            return ToolResult.error_result(ToolErrorCode.INVALID_ARGUMENT, error)

        job_id = db.create_cron_job(
            name=(name or prompt.strip()[:60]),
            prompt=prompt.strip(),
            cron_expr=spec.get("cron_expr", ""),
            schedule_kind=spec["schedule_kind"],
            interval_minutes=spec.get("interval_minutes"),
            run_at=spec.get("run_at"),
            timezone=timezone,
            chat_id=chat_id if bind_to_chat else None,
            context_mode="bound" if bind_to_chat else "isolated",
            suppress_ok=bool(quiet_if_nothing_to_report) and bind_to_chat,
            delivery_mode="none" if bind_to_chat else "announce",
            source=AGENT_SOURCE,
        )

        job = db.get_cron_job(job_id)
        next_run = compute_next_run(job)
        if next_run is None:
            db.delete_cron_job(job_id)
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "That schedule has no future run time.",
            )
        db.update_cron_job_run_state(job_id, next_run_at=next_run)

        where = "in this conversation" if bind_to_chat else "in its own isolated chat"
        return ToolResult.success_result(
            f"Scheduled #{job_id} '{job.name}' {where}, "
            f"{self._describe(job)}. Next run {next_run.isoformat(timespec='minutes')}.",
            metadata={"task_id": job_id, "next_run_at": next_run.isoformat()},
        )

    def _list(self, chat_id: str) -> ToolResult:
        db = get_database()
        jobs = db.list_cron_jobs_for_chat(chat_id, active_only=True)
        if not jobs:
            return ToolResult.success_result("No scheduled tasks on this chat.")

        lines = []
        for job in jobs:
            nxt = (
                job.next_run_at.isoformat(timespec="minutes")
                if job.next_run_at
                else "unscheduled"
            )
            lines.append(
                f"  [#{job.id}] {job.name} — {self._describe(job)}, "
                f"next {nxt} (source: {job.source})"
            )
        body = "\n".join(lines)
        return ToolResult.success_result(f"{len(jobs)} scheduled task(s):\n{body}")

    def _cancel(self, chat_id: str, task_id: Optional[int]) -> ToolResult:
        job, error = self._own_task(chat_id, task_id)
        if error:
            return error
        get_database().delete_cron_job(job.id)
        return ToolResult.success_result(f"Cancelled #{job.id} '{job.name}'.")

    def _update(
        self,
        chat_id: str,
        task_id: Optional[int],
        every_minutes: Optional[int],
        cron: Optional[str],
        prompt: Optional[str],
        name: Optional[str],
    ) -> ToolResult:
        job, error = self._own_task(chat_id, task_id)
        if error:
            return error

        updates: dict = {}
        if name:
            updates["name"] = name
        if prompt and prompt.strip():
            updates["prompt"] = prompt.strip()

        if every_minutes is not None or cron is not None:
            spec, spec_error = self._resolve_schedule(
                in_minutes=None, at=None, every_minutes=every_minutes, cron=cron
            )
            if spec_error:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT, spec_error
                )
            updates.update(
                {
                    "schedule_kind": spec["schedule_kind"],
                    "cron_expr": spec.get("cron_expr", ""),
                    "interval_minutes": spec.get("interval_minutes"),
                }
            )

        if not updates:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Nothing to update: pass name, prompt, every_minutes or cron.",
            )

        db = get_database()
        db.update_cron_job(job.id, **updates)
        job = db.get_cron_job(job.id)
        next_run = compute_next_run(job)
        if next_run is not None:
            db.update_cron_job_run_state(job.id, next_run_at=next_run)
        return ToolResult.success_result(
            f"Updated #{job.id} '{job.name}' — {self._describe(job)}."
        )

    # -- helpers -------------------------------------------------------------

    def _own_task(self, chat_id: str, task_id: Optional[int]):
        """Resolve a task id, refusing anything this chat doesn't own.

        A chat can only touch its own tasks. In particular the agent may not
        cancel a heartbeat or a cron job a human configured -- those are the
        user's, and silently removing one would be a surprise.
        """
        if task_id is None:
            return None, ToolResult.error_result(
                ToolErrorCode.MISSING_REQUIRED_PARAM, "task_id is required."
            )
        job = get_database().get_cron_job(task_id)
        if not job or job.chat_id != chat_id:
            return None, ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                f"No scheduled task #{task_id} on this chat.",
            )
        if job.source != AGENT_SOURCE:
            return None, ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED,
                f"Task #{task_id} was set up by the user ({job.source}); "
                "ask them to change it rather than changing it yourself.",
            )
        return job, None

    def _resolve_schedule(
        self,
        *,
        in_minutes: Optional[int],
        at: Optional[str],
        every_minutes: Optional[int],
        cron: Optional[str],
    ):
        """Validate one schedule spec, returning (fields, error_message)."""
        if in_minutes is not None:
            if in_minutes < MIN_DELAY_MINUTES:
                return None, f"in_minutes must be at least {MIN_DELAY_MINUTES}."
            return {
                "schedule_kind": "once",
                "run_at": datetime.now() + timedelta(minutes=in_minutes),
            }, None

        if at is not None:
            try:
                run_at = datetime.fromisoformat(at)
            except ValueError:
                return None, f"Could not parse {at!r} as an ISO 8601 timestamp."
            if run_at.tzinfo is not None:
                run_at = run_at.astimezone().replace(tzinfo=None)
            if run_at <= datetime.now():
                return None, f"{at} is in the past."
            return {"schedule_kind": "once", "run_at": run_at}, None

        if every_minutes is not None:
            if every_minutes < MIN_INTERVAL_MINUTES:
                return None, (
                    f"every_minutes must be at least {MIN_INTERVAL_MINUTES} "
                    "so a repeating task can't wake you in a tight loop."
                )
            return {
                "schedule_kind": "interval",
                "interval_minutes": every_minutes,
            }, None

        if not croniter.is_valid(cron):
            return None, f"Invalid cron expression: {cron}"
        iterator = croniter(cron, datetime.now())
        first = iterator.get_next(datetime)
        period = (iterator.get_next(datetime) - first).total_seconds()
        if period < MIN_CRON_PERIOD_SECONDS:
            return None, (
                f"{cron!r} fires every {int(period)}s; the floor is "
                f"{MIN_CRON_PERIOD_SECONDS}s."
            )
        return {"schedule_kind": "cron", "cron_expr": cron}, None

    @staticmethod
    def _describe(job) -> str:
        kind = job.schedule_kind or "cron"
        if kind == "once":
            when = job.run_at.isoformat(timespec="minutes") if job.run_at else "unset"
            return f"once at {when}"
        if kind == "interval":
            return f"every {job.interval_minutes}m"
        tz = f" ({job.timezone})" if job.timezone else ""
        return f"cron {job.cron_expr}{tz}"
