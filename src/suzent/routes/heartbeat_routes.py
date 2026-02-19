"""
Heartbeat system API routes.
"""

from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.heartbeat import HeartbeatRunner, get_active_heartbeat


def _get_runner() -> Optional[HeartbeatRunner]:
    """Return the active HeartbeatRunner, or None."""
    return get_active_heartbeat()


def _not_initialized() -> JSONResponse:
    return JSONResponse({"error": "HeartbeatRunner not initialized"}, status_code=503)


_DISABLED_STATUS = {
    "enabled": False,
    "running": False,
    "interval_minutes": 0,
    "heartbeat_md_exists": False,
    "last_run_at": None,
    "last_result": None,
    "last_error": None,
}


async def get_heartbeat_status(request: Request) -> JSONResponse:
    """Get heartbeat system status."""
    if not (runner := _get_runner()):
        return JSONResponse(_DISABLED_STATUS)
    return JSONResponse(runner.get_status())


async def enable_heartbeat(request: Request) -> JSONResponse:
    """Enable the heartbeat system."""
    if not (runner := _get_runner()):
        return _not_initialized()

    if not runner.heartbeat_md_path.exists():
        return JSONResponse(
            {"error": "HEARTBEAT.md not found. Create /shared/HEARTBEAT.md to enable."},
            status_code=400,
        )

    await runner.enable()
    return JSONResponse({"success": True})


async def disable_heartbeat(request: Request) -> JSONResponse:
    """Disable the heartbeat system."""
    if not (runner := _get_runner()):
        return _not_initialized()
    await runner.disable()
    return JSONResponse({"success": True})


async def trigger_heartbeat(request: Request) -> JSONResponse:
    """Trigger an immediate heartbeat tick."""
    if not (runner := _get_runner()):
        return _not_initialized()
    await runner.trigger_now()
    return JSONResponse({"success": True})


async def get_heartbeat_md(request: Request) -> JSONResponse:
    """Read the HEARTBEAT.md content."""
    if not (runner := _get_runner()):
        return JSONResponse({"content": "", "exists": False})

    path = runner.heartbeat_md_path
    if not path.exists():
        return JSONResponse({"content": "", "exists": False})

    try:
        content = path.read_text(encoding="utf-8")
        return JSONResponse({"content": content, "exists": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def save_heartbeat_md(request: Request) -> JSONResponse:
    """Write the HEARTBEAT.md content."""
    if not (runner := _get_runner()):
        return _not_initialized()

    body = await request.json()
    content = body.get("content", "")

    path = runner.heartbeat_md_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
