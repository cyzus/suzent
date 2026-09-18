"""Operational control of the background service, over HTTP.

The desktop app manages the service through Tauri commands that shell out to
``suzent service``. A browser has no such channel, and the browser is exactly
the client that needs one: the web console exists to run a headless host from
somewhere else, where "is it up, why did it stop, restart it" is the whole job.

These routes wrap the same ``ServiceController`` the CLI uses, so there is one
implementation of what installing or restarting means.

Two of them can act on the very process handling the request. ``restart``
therefore answers *before* it does anything and lets the client poll; disabling
is refused outright, because a browser that turns off the service serving it
has no way left to turn it back on.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import RUNTIME_DIR
from suzent.logger import get_logger
from suzent.service import get_service_controller
from suzent.service.state import read_process_state

logger = get_logger(__name__)

LOG_PATH = RUNTIME_DIR / "server.log"

# The service logs through the same formatter the terminal gets, so the file
# carries colour codes. A terminal renders them; a <pre> shows them as litter
# like "[32m[0m" in front of every line.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Enough to see a startup sequence or a traceback, bounded so a wedged log
# cannot turn one request into a multi-megabyte response.
DEFAULT_LOG_LINES = 200
MAX_LOG_LINES = 2000

# How long to wait before acting on a request that stops this process. The
# response has to be written and flushed to the client first, or the console
# sees a dropped connection and cannot tell a successful restart from a crash.
_SELF_ACTION_DELAY_SECONDS = 0.5


def _serving_process_is_the_service() -> bool:
    """Whether this very process is the background service.

    True on a headless host, where the service both runs the agent and serves
    the console. False when the console is served by a separate ``suzent
    serve`` or by the desktop app's backend, in which case the service is
    someone else and can be stopped freely.
    """
    if os.getenv("SUZENT_RUN_MODE") != "service":
        return False
    state = read_process_state()
    return state is not None and state.pid == os.getpid()


def _status_payload() -> dict:
    controller = get_service_controller()
    payload = controller.status().to_dict()
    payload["self_managed"] = _serving_process_is_the_service()
    payload["log_path"] = str(LOG_PATH)
    payload["log_available"] = LOG_PATH.is_file()
    return payload


async def get_ops_status(_request: Request) -> JSONResponse:
    """Service status, plus whether this process is the service being reported."""
    try:
        return JSONResponse(await asyncio.to_thread(_status_payload))
    except Exception as exc:  # platform managers raise a variety of OS errors
        logger.warning(f"Service status failed: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


def _tail(path: Path, lines: int) -> list[str]:
    """The last ``lines`` lines of a file, read from the end.

    Reads backwards in blocks so a large log costs the size of its tail rather
    than its whole length.
    """
    if not path.is_file():
        return []
    block = 64 * 1024
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        remaining = handle.tell()
        chunks: list[bytes] = []
        found = 0
        while remaining > 0 and found <= lines:
            step = min(block, remaining)
            remaining -= step
            handle.seek(remaining)
            chunks.append(handle.read(step))
            found += chunks[-1].count(b"\n")
        data = b"".join(reversed(chunks))
    # errors="replace": a log truncated mid-character must still be readable.
    text = _ANSI.sub("", data.decode("utf-8", errors="replace"))
    return text.splitlines()[-lines:]


async def get_ops_logs(request: Request) -> JSONResponse:
    """Tail the service log.

    The log is the only account of what a headless host did before it stopped
    answering, so the console shows it rather than making an operator find the
    file over SSH.
    """
    try:
        requested = int(request.query_params.get("lines", DEFAULT_LOG_LINES))
    except ValueError:
        requested = DEFAULT_LOG_LINES
    lines = max(1, min(requested, MAX_LOG_LINES))

    try:
        tail = await asyncio.to_thread(_tail, LOG_PATH, lines)
    except OSError as exc:
        logger.warning(f"Reading {LOG_PATH} failed: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse(
        {
            "path": str(LOG_PATH),
            "available": LOG_PATH.is_file(),
            "lines": tail,
            "truncated": len(tail) >= lines,
        }
    )


async def restart_ops_service(_request: Request) -> JSONResponse:
    """Restart the background service.

    When this process *is* the service, the restart is deliberately deferred
    past the response: the client is told to expect a gap and poll the status
    route, which is the only way it can distinguish a restart it asked for from
    a host that fell over.
    """
    controller = get_service_controller()
    try:
        installed = await asyncio.to_thread(controller.platform_manager.is_installed)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    if not installed:
        return JSONResponse({"error": "service_not_installed"}, status_code=409)

    if not _serving_process_is_the_service():
        try:
            await asyncio.to_thread(controller.restart)
        except Exception as exc:
            logger.warning(f"Service restart failed: {exc}")
            return JSONResponse({"error": str(exc)}, status_code=500)
        return JSONResponse(await asyncio.to_thread(_status_payload))

    async def _restart_after_response() -> None:
        await asyncio.sleep(_SELF_ACTION_DELAY_SECONDS)
        try:
            await asyncio.to_thread(controller.restart)
        except Exception as exc:
            logger.error(f"Deferred self-restart failed: {exc}")

    # Held nowhere on purpose: this task is meant to outlive the request, and
    # the process it restarts is the one that would have awaited it.
    asyncio.create_task(_restart_after_response())
    logger.info("Restarting this service at the console's request")
    return JSONResponse({"status": "restarting", "self_managed": True}, status_code=202)


async def set_ops_service_enabled(request: Request) -> JSONResponse:
    """Install or uninstall the background service.

    Disabling is refused when this process is the service. The request would
    succeed and then take the console offline permanently -- re-enabling needs
    a shell on the host, which is the one thing a remote browser does not have.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        return JSONResponse({"error": "enabled_must_be_boolean"}, status_code=400)
    enabled = body["enabled"]

    if not enabled and _serving_process_is_the_service():
        return JSONResponse(
            {
                "error": "would_disable_self",
                "detail": (
                    "This service is serving the console. Disabling it here "
                    "would leave no way to re-enable it remotely; run "
                    "'suzent service uninstall' on the host instead."
                ),
            },
            status_code=409,
        )

    controller = get_service_controller()
    action = "install" if enabled else "uninstall"
    try:
        if enabled:
            await asyncio.to_thread(controller.install)
        else:
            await asyncio.to_thread(controller.uninstall)
    except Exception as exc:
        logger.warning(f"Service {action} failed: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)

    return JSONResponse(await asyncio.to_thread(_status_payload))
