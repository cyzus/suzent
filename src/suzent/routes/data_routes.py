from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.data_portability import (
    export_data,
    get_data_status,
    import_data,
    preview_import,
    sync_pull,
    sync_push,
)


async def get_data_path(request: Request) -> JSONResponse:
    status = get_data_status()
    return JSONResponse(status.model_dump())


async def get_data_status_route(request: Request) -> JSONResponse:
    status = get_data_status()
    return JSONResponse(status.model_dump())


async def export_data_route(request: Request) -> JSONResponse:
    payload = await _json_payload(request)
    output = payload.get("output")
    result = export_data(Path(output) if output else None)
    return JSONResponse(result.model_dump())


async def import_data_dry_run_route(request: Request) -> JSONResponse:
    payload = await _json_payload(request)
    archive = _archive_from_payload(payload)
    result = preview_import(archive)
    return JSONResponse(result.model_dump())


async def import_data_route(request: Request) -> JSONResponse:
    payload = await _json_payload(request)
    archive = _archive_from_payload(payload)
    result = import_data(archive, mode=payload.get("mode", "replace"))
    return JSONResponse(result.model_dump())


async def sync_push_route(request: Request) -> JSONResponse:
    payload = await _json_payload(request)
    target = _target_from_payload(payload)
    result = sync_push(target)
    return JSONResponse(result.model_dump())


async def sync_pull_route(request: Request) -> JSONResponse:
    payload = await _json_payload(request)
    target = _target_from_payload(payload)
    result = sync_pull(target, dry_run=bool(payload.get("dry_run", False)))
    return JSONResponse(result.model_dump())


async def _json_payload(request: Request) -> dict:
    try:
        payload = await request.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _archive_from_payload(payload: dict) -> Path:
    archive = payload.get("archive") or payload.get("archive_path")
    if not archive:
        raise ValueError("archive is required")
    return Path(str(archive))


def _target_from_payload(payload: dict) -> Path:
    target = payload.get("target") or payload.get("target_path")
    if not target:
        raise ValueError("target is required")
    return Path(str(target))
