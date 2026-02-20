"""
Cron job management API routes.
"""

from datetime import datetime

from croniter import croniter
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.database import CronJobModel, get_database


def _job_to_dict(job: CronJobModel) -> dict:
    """Serialize a CronJobModel to a JSON-safe dict."""
    return {
        "id": job.id,
        "name": job.name,
        "cron_expr": job.cron_expr,
        "prompt": job.prompt,
        "active": job.active,
        "delivery_mode": job.delivery_mode,
        "model_override": job.model_override,
        "retry_count": job.retry_count,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "last_result": job.last_result,
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


async def list_cron_jobs(request: Request) -> JSONResponse:
    """List all cron jobs."""
    db = get_database()
    jobs = db.list_cron_jobs()
    return JSONResponse({"jobs": [_job_to_dict(j) for j in jobs]})


async def create_cron_job(request: Request) -> JSONResponse:
    """Create a new cron job."""
    data = await request.json()
    name = data.get("name")
    cron_expr = data.get("cron_expr")
    prompt = data.get("prompt")

    if not name or not cron_expr or not prompt:
        return JSONResponse(
            {"error": "Missing required fields: name, cron_expr, prompt"},
            status_code=400,
        )

    # Validate cron expression
    if not croniter.is_valid(cron_expr):
        return JSONResponse(
            {"error": f"Invalid cron expression: {cron_expr}"}, status_code=400
        )

    db = get_database()
    now = datetime.now()
    next_run = croniter(cron_expr, now).get_next(datetime)

    job_id = db.create_cron_job(
        name=name,
        cron_expr=cron_expr,
        prompt=prompt,
        active=data.get("active", True),
        delivery_mode=data.get("delivery_mode", "announce"),
        model_override=data.get("model_override"),
    )

    # Set initial next_run_at
    db.update_cron_job_run_state(job_id, next_run_at=next_run)

    job = db.get_cron_job(job_id)
    return JSONResponse({"job": _job_to_dict(job)}, status_code=201)


async def update_cron_job(request: Request) -> JSONResponse:
    """Update a cron job."""
    job_id = int(request.path_params["job_id"])
    data = await request.json()

    db = get_database()
    job = db.get_cron_job(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    # Validate cron expression if being updated
    if "cron_expr" in data:
        if not croniter.is_valid(data["cron_expr"]):
            return JSONResponse(
                {"error": f"Invalid cron expression: {data['cron_expr']}"},
                status_code=400,
            )
        # Recompute next_run_at
        now = datetime.now()
        next_run = croniter(data["cron_expr"], now).get_next(datetime)
        db.update_cron_job_run_state(job_id, next_run_at=next_run)

    _ALLOWED_FIELDS = {
        "name",
        "cron_expr",
        "prompt",
        "active",
        "delivery_mode",
        "model_override",
    }
    updates = {k: v for k, v in data.items() if k in _ALLOWED_FIELDS}

    if updates:
        db.update_cron_job(job_id, **updates)

    job = db.get_cron_job(job_id)
    return JSONResponse({"job": _job_to_dict(job)})


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
