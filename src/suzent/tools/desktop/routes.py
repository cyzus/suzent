"""HTTP endpoints for the consented agent-desktop install."""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger
from suzent.tools.desktop.install import (
    CONSENT_TEXT,
    DesktopInstallError,
    install_release,
    runtime_status,
)

logger = get_logger(__name__)


async def desktop_runtime(_request: Request) -> JSONResponse:
    return JSONResponse(runtime_status())


async def desktop_runtime_install(request: Request) -> JSONResponse:
    """Download the pinned release. ``confirmed`` must be true.

    The settings page and the CLI set that flag only after the user agrees.
    A tool call never hits this route.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = None
    if not isinstance(payload, dict) or payload.get("confirmed") is not True:
        return JSONResponse(
            {
                "error": "Confirmation is required before agent-desktop is installed.",
                "consent": CONSENT_TEXT,
            },
            status_code=400,
        )
    try:
        result = await asyncio.to_thread(install_release)
    except DesktopInstallError as exc:
        logger.warning("agent-desktop install failed: {}", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse(result)
