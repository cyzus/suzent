"""Inbound webhook endpoint: ``POST /hooks/{token}`` fires a webhook task.

The route sits outside the device-token auth boundary because external
services can't hold a Suzent device grant. The unguessable token in the URL is
the credential, checked here against the hash stored on the task.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.webhooks import (
    MAX_PAYLOAD_BYTES,
    WEBHOOK_KIND,
    format_webhook_payload,
    hash_webhook_token,
)
from suzent.database import get_database
from suzent.logger import get_logger

logger = get_logger(__name__)

_NOT_FOUND = {"error": "Not found"}


async def _read_capped_body(request: Request) -> bytes | None:
    """The request body, or None once it passes the size cap."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_PAYLOAD_BYTES:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PAYLOAD_BYTES:
            return None
    return bytes(body)


async def receive_webhook(request: Request) -> JSONResponse:
    """Run the webhook task that owns this URL with the request as its input."""
    token = request.path_params["token"]
    db = get_database()
    job = db.find_cron_job_by_webhook_hash(hash_webhook_token(token))
    # An unknown token, a paused task and a task that is no longer a webhook
    # all answer the same, so the endpoint can't be used to probe for tasks.
    if job is None or not job.active or job.schedule_kind != WEBHOOK_KIND:
        return JSONResponse(_NOT_FOUND, status_code=404)

    body = await _read_capped_body(request)
    if body is None:
        return JSONResponse(
            {"error": f"Payload larger than {MAX_PAYLOAD_BYTES} bytes"},
            status_code=413,
        )

    from suzent.core.scheduler import get_active_scheduler

    scheduler = get_active_scheduler()
    if scheduler is None:
        return JSONResponse({"error": "Scheduler not running"}, status_code=503)

    headers = {k.lower(): v for k, v in request.headers.items()}
    if not scheduler.fire_webhook(job, format_webhook_payload(body, headers)):
        return JSONResponse(
            {"error": "This webhook is already running; try again later"},
            status_code=429,
            headers={"Retry-After": "30"},
        )

    logger.info(f"Webhook task {job.id} triggered ({len(body)} bytes)")
    return JSONResponse({"accepted": True, "job_id": job.id}, status_code=202)
