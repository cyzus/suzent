"""Inbound webhook endpoint: ``POST /hooks/{token}`` fires a webhook task or ingests into Mailbox."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.mailbox import ingest_mailbox_event, is_mailbox_token
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
    """Run the webhook task that owns this URL, or route via the unified Mailbox."""
    token = request.path_params["token"]
    db = get_database()

    if is_mailbox_token(token):
        body = await _read_capped_body(request)
        if body is None:
            return JSONResponse(
                {"error": f"Payload larger than {MAX_PAYLOAD_BYTES} bytes"},
                status_code=413,
            )
        headers = {k.lower(): v for k, v in request.headers.items()}
        item = await ingest_mailbox_event(
            source_kind="webhook",
            body_bytes=body,
            headers=headers,
        )
        logger.info(
            f"Mailbox webhook #{item.id} ingested ({len(body)} bytes, status={item.route_status}, target={item.target_chat_id})"
        )
        return JSONResponse(
            {
                "accepted": True,
                "item_id": item.id,
                "route_status": item.route_status,
                "target_chat_id": item.target_chat_id,
            },
            status_code=202,
        )

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
    formatted = format_webhook_payload(body, headers)
    if not scheduler.fire_webhook(job, formatted):
        return JSONResponse(
            {"error": "This webhook is already running; try again later"},
            status_code=429,
            headers={"Retry-After": "30"},
        )

    bound = (job.context_mode or "isolated") == "bound" and bool(job.chat_id)
    target_chat_id = job.chat_id if bound else f"cron-{job.id}"
    try:
        await ingest_mailbox_event(
            source_kind="webhook",
            body_bytes=body,
            headers=headers,
            fallback_source=job.name,
            preferred_chat_id=target_chat_id,
            custom_prompt=job.prompt,
            dispatch=False,
        )
    except Exception as exc:
        logger.debug(f"Could not record job webhook in mailbox: {exc}")

    logger.info(f"Webhook task {job.id} triggered ({len(body)} bytes)")
    return JSONResponse({"accepted": True, "job_id": job.id}, status_code=202)
