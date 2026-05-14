from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.codex_session import get_codex_session_service
from suzent.database import get_database


def _connector_config_payload() -> dict[str, Any]:
    config = get_database().get_codex_connector_config()
    if config is None:
        return {"enabled": False, "codex_home": None}
    return {
        "enabled": config.enabled,
        "codex_home": config.codex_home,
        "last_status": config.last_status,
        "last_checked_at": config.last_checked_at.isoformat()
        if config.last_checked_at
        else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


async def _request_codex_home(request: Request) -> str | None:
    if request.method == "GET":
        raw = request.query_params.get("codex_home")
        return raw.strip() if raw else None

    try:
        payload = await request.json()
    except Exception:
        return None
    raw = payload.get("codex_home") if isinstance(payload, dict) else None
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


async def get_codex_status(request: Request) -> JSONResponse:
    codex_home = await _request_codex_home(request)
    stored_config = get_database().get_codex_connector_config()
    effective_home = codex_home or (stored_config.codex_home if stored_config else None)

    service = get_codex_session_service(effective_home)
    status = await asyncio.to_thread(service.get_status)
    checked_at = datetime.now()

    get_database().save_codex_connector_config(
        enabled=status.connected,
        codex_home=effective_home,
        last_status=status.status,
        last_checked_at=checked_at,
    )
    status.checked_at = checked_at.isoformat()

    return JSONResponse(
        {"status": status.model_dump(), "config": _connector_config_payload()}
    )


async def start_codex_login(request: Request) -> JSONResponse:
    codex_home = await _request_codex_home(request)
    service = get_codex_session_service(codex_home)
    result = await asyncio.to_thread(service.start_login)
    return JSONResponse(result.model_dump(), status_code=200 if result.success else 400)


async def start_codex_device_login(request: Request) -> JSONResponse:
    codex_home = await _request_codex_home(request)
    service = get_codex_session_service(codex_home)
    result = await asyncio.to_thread(service.start_login, device_auth=True)
    return JSONResponse(result.model_dump(), status_code=200 if result.success else 400)


async def logout_codex(request: Request) -> JSONResponse:
    codex_home = await _request_codex_home(request)
    stored_config = get_database().get_codex_connector_config()
    effective_home = codex_home or (stored_config.codex_home if stored_config else None)

    service = get_codex_session_service(effective_home)
    result = await asyncio.to_thread(service.logout)
    get_database().save_codex_connector_config(
        enabled=False,
        codex_home=effective_home,
        last_status=result.status.status if result.status else "not_logged_in",
        last_checked_at=datetime.now(),
    )
    return JSONResponse(result.model_dump(), status_code=200 if result.success else 400)
