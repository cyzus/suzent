"""
Cron job management API routes.
"""

from datetime import datetime

from croniter import croniter
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.scheduler import compute_next_run
from suzent.core.stream_registry import is_background_streaming
from suzent.database import ChatDatabase, CronJobModel, get_database


def _task_chat_id(job: CronJobModel) -> str:
    """The chat a task runs in: the one it is bound to, else its own."""
    if (job.context_mode or "isolated") == "bound" and job.chat_id:
        return job.chat_id
    return f"cron-{job.id}"


def _job_to_dict(job: CronJobModel, db: ChatDatabase) -> dict:
    """Serialize a CronJobModel to a JSON-safe dict."""
    chat_id = _task_chat_id(job)
    chat = db.get_chat(chat_id)
    latest_runs = db.list_cron_runs(job.id, limit=1)
    latest_run = latest_runs[0] if latest_runs else None
    return {
        "id": job.id,
        "name": job.name,
        "cron_expr": job.cron_expr,
        "prompt": job.prompt,
        "active": job.active,
        "delivery_mode": job.delivery_mode,
        "model_override": job.model_override,
        "retry_count": job.retry_count,
        "schedule_kind": job.schedule_kind,
        "interval_minutes": job.interval_minutes,
        "run_at": job.run_at.isoformat() if job.run_at else None,
        "timezone": job.timezone,
        "jitter_seconds": job.jitter_seconds,
        "catch_up": job.catch_up,
        "chat_id": job.chat_id,
        "context_mode": job.context_mode,
        "suppress_ok": job.suppress_ok,
        "source": job.source,
        "chat_title": chat.title if chat else None,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "last_result": job.last_result,
        "last_error": job.last_error,
        "chat_updated_at": chat.updated_at.isoformat() if chat else None,
        "last_run_finished_at": (
            latest_run.finished_at.isoformat()
            if latest_run and latest_run.finished_at
            else None
        ),
        "is_running": is_background_streaming(chat_id),
        "unread_count": (chat.config or {}).get("unread_count", 0) if chat else 0,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


async def list_cron_jobs(request: Request) -> JSONResponse:
    """List all cron jobs."""
    db = get_database()
    jobs = db.list_cron_jobs()
    return JSONResponse({"jobs": [_job_to_dict(j, db) for j in jobs]})


async def create_cron_job(request: Request) -> JSONResponse:
    """Create a new cron job."""
    data = await request.json()
    name = data.get("name")
    prompt = data.get("prompt")
    schedule_kind = data.get("schedule_kind", "cron")
    cron_expr = data.get("cron_expr") or ""

    if not name or not prompt:
        return JSONResponse(
            {"error": "Missing required fields: name, prompt"}, status_code=400
        )

    error = _validate_schedule(schedule_kind, cron_expr, data)
    if error:
        return JSONResponse({"error": error}, status_code=400)

    run_at = _parse_run_at(data.get("run_at"))
    chat_id = data.get("chat_id")
    context_mode = data.get("context_mode") or ("bound" if chat_id else "isolated")
    if context_mode == "bound" and not chat_id:
        return JSONResponse({"error": "A bound task needs a chat_id"}, status_code=400)

    db = get_database()
    job_id = db.create_cron_job(
        name=name,
        cron_expr=cron_expr,
        prompt=prompt,
        active=data.get("active", True),
        delivery_mode=data.get("delivery_mode", "announce"),
        model_override=data.get("model_override"),
        schedule_kind=schedule_kind,
        interval_minutes=data.get("interval_minutes"),
        run_at=run_at,
        timezone=data.get("timezone"),
        jitter_seconds=data.get("jitter_seconds", 0),
        catch_up=data.get("catch_up", "skip"),
        chat_id=chat_id,
        context_mode=context_mode,
        suppress_ok=bool(data.get("suppress_ok", False)),
        source=data.get("source", "user"),
    )

    # Set initial next_run_at
    job = db.get_cron_job(job_id)
    next_run = compute_next_run(job)
    if next_run is None:
        db.delete_cron_job(job_id)
        return JSONResponse(
            {"error": "That schedule has no future run time"}, status_code=400
        )
    db.update_cron_job_run_state(job_id, next_run_at=next_run)

    job = db.get_cron_job(job_id)
    return JSONResponse({"job": _job_to_dict(job, db)}, status_code=201)


def _parse_run_at(raw):
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _validate_schedule(schedule_kind: str, cron_expr: str, data: dict):
    """Return an error message for an unusable schedule, or None."""
    if schedule_kind == "cron":
        if not cron_expr:
            return "cron_expr is required for a cron schedule"
        if not croniter.is_valid(cron_expr):
            return f"Invalid cron expression: {cron_expr}"
        return None
    if schedule_kind == "interval":
        minutes = data.get("interval_minutes")
        if not isinstance(minutes, int) or minutes < 1:
            return "interval_minutes must be a positive integer"
        return None
    if schedule_kind == "once":
        if _parse_run_at(data.get("run_at")) is None:
            return "run_at must be an ISO 8601 timestamp for a one-shot task"
        return None
    return f"Unknown schedule_kind: {schedule_kind}"


async def update_cron_job(request: Request) -> JSONResponse:
    """Update a cron job."""
    job_id = int(request.path_params["job_id"])
    data = await request.json()

    db = get_database()
    job = db.get_cron_job(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    _ALLOWED_FIELDS = {
        "name",
        "cron_expr",
        "prompt",
        "active",
        "delivery_mode",
        "model_override",
        "schedule_kind",
        "interval_minutes",
        "timezone",
        "jitter_seconds",
        "catch_up",
        "chat_id",
        "context_mode",
        "suppress_ok",
    }
    updates = {k: v for k, v in data.items() if k in _ALLOWED_FIELDS}
    if "run_at" in data:
        updates["run_at"] = _parse_run_at(data["run_at"])

    # Validate the schedule as it will look after the patch, not just the
    # fields that happen to be in this request.
    schedule_touched = bool(
        {"schedule_kind", "cron_expr", "interval_minutes", "run_at"} & set(data)
    )
    if schedule_touched:
        # Validate what was submitted, not what survived parsing. A run_at the
        # client sent but we could not parse lands in updates as None; falling
        # back to the stored timestamp here would pass validation and then
        # write the None, silently unscheduling the task behind a 200.
        if "run_at" in data:
            submitted_run_at = updates["run_at"]
        else:
            submitted_run_at = job.run_at
        merged = {
            "interval_minutes": updates.get("interval_minutes", job.interval_minutes),
            "run_at": submitted_run_at.isoformat() if submitted_run_at else None,
        }
        kind = updates.get("schedule_kind", job.schedule_kind or "cron")
        expr = updates.get("cron_expr", job.cron_expr or "")
        error = _validate_schedule(kind, expr, merged)
        if error:
            return JSONResponse({"error": error}, status_code=400)

    if updates:
        db.update_cron_job(job_id, **updates)

    job = db.get_cron_job(job_id)
    if schedule_touched:
        next_run = compute_next_run(job)
        db.update_cron_job_run_state(
            job_id, next_run_at=next_run, clear_next_run=next_run is None
        )
        job = db.get_cron_job(job_id)

    return JSONResponse({"job": _job_to_dict(job, db)})


async def delete_cron_job(request: Request) -> JSONResponse:
    """Delete a cron job."""
    job_id = int(request.path_params["job_id"])
    db = get_database()
    if db.delete_cron_job(job_id):
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Job not found"}, status_code=404)


async def trigger_cron_job(request: Request) -> JSONResponse:
    """Trigger immediate execution of a cron job."""
    job_id = int(request.path_params["job_id"])
    db = get_database()
    job = db.get_cron_job(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    from suzent.core.scheduler import get_active_scheduler

    scheduler = get_active_scheduler()
    if not scheduler:
        return JSONResponse({"error": "Scheduler not running"}, status_code=503)

    await scheduler.trigger_job_now(job_id)
    return JSONResponse({"success": True, "message": f"Job {job_id} triggered"})


async def get_cron_status(request: Request) -> JSONResponse:
    """Get scheduler status."""
    from suzent.core.scheduler import get_active_scheduler

    scheduler = get_active_scheduler()
    db = get_database()
    jobs = db.list_cron_jobs()
    active_count = sum(1 for j in jobs if j.active)

    return JSONResponse(
        {
            "scheduler_running": scheduler is not None and scheduler._running,
            "total_jobs": len(jobs),
            "active_jobs": active_count,
        }
    )


async def get_cron_notifications(request: Request) -> JSONResponse:
    """Drain pending cron notifications."""
    from suzent.core.scheduler import get_active_scheduler

    scheduler = get_active_scheduler()
    if not scheduler:
        return JSONResponse({"notifications": []})

    notifications = scheduler.drain_notifications()
    return JSONResponse({"notifications": notifications})


async def get_cron_job_runs(request: Request) -> JSONResponse:
    """Get run history for a cron job."""
    job_id = int(request.path_params["job_id"])
    limit = int(request.query_params.get("limit", "20"))
    db = get_database()
    runs = db.list_cron_runs(job_id, limit=limit)
    return JSONResponse({"runs": [_run_to_dict(r) for r in runs]})


async def install_cron_presets(request: Request) -> JSONResponse:
    """Install or update builtin cron presets."""
    try:
        data = await request.json()
    except Exception:
        data = {}

    activate_existing = bool(data.get("activate_existing", False))

    from suzent.core.scheduler import ensure_cron_presets

    db = get_database()
    result = ensure_cron_presets(db, activate_existing=activate_existing)
    return JSONResponse(result)


def _run_to_dict(run) -> dict:
    """Serialize a CronRunModel to a JSON-safe dict."""
    return {
        "id": run.id,
        "job_id": run.job_id,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "result": run.result,
        "error": run.error,
    }
