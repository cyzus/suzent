from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.sync.models import SyncConflict, SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME
from suzent.sync.service import GitHubSyncService


def _service(request: Request) -> GitHubSyncService:
    service = getattr(request.app.state, "github_sync_service", None)
    if service is None:
        service = GitHubSyncService()
        request.app.state.github_sync_service = service
    return service


async def get_sync_status(request: Request) -> JSONResponse:
    return JSONResponse(
        _service(request).status(request.query_params.get("profile_id"))
    )


async def get_sync_quickstart_info(request: Request) -> JSONResponse:
    return JSONResponse(_service(request).quickstart_info())


async def quickstart_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        return JSONResponse(
            service.quickstart(
                repo_name=payload.get("repo_name"),
                authenticate_github=bool(payload.get("authenticate_github", True)),
                github_token=payload.get("github_token"),
                repo_path=payload.get("repo_path"),
                branch=payload.get("branch"),
                remote=payload.get("remote"),
                auto_sync_enabled=bool(payload.get("auto_sync_enabled", False)),
                auto_resolve_enabled=bool(payload.get("auto_resolve_enabled", True)),
                interval_hours=int(payload.get("interval_hours", 4)),
            )
        )
    except Exception as exc:
        return _error_response(str(exc), 400)


async def get_sync_profiles(request: Request) -> JSONResponse:
    profiles = _service(request).list_profiles()
    return JSONResponse({"profiles": [p.model_dump(mode="json") for p in profiles]})


async def create_sync_profile(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        profile = SyncProfile.model_validate(payload)
        saved = _service(request).create_profile(profile)
        return JSONResponse(saved.model_dump(mode="json"))
    except Exception as exc:
        return _error_response(str(exc), 400)


async def validate_sync_profile(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        profile = _profile_from_payload(service, payload)
        return JSONResponse(service.validate(profile))
    except FileNotFoundError as exc:
        return _error_response(str(exc), 404)
    except Exception as exc:
        return _error_response(str(exc), 400)


async def preview_sync_pull(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        return JSONResponse(_service(request).preview_pull(payload.get("profile_id")))
    except Exception as exc:
        return _error_response(str(exc), 400)


async def pull_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        return JSONResponse(
            await service.pull(
                payload.get("profile_id"),
                shibboleth=_shibboleth_from_payload(payload),
            )
        )
    except Exception as exc:
        return _error_response(str(exc), 400)


async def push_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        return JSONResponse(
            await service.push(
                payload.get("profile_id"),
                shibboleth=_shibboleth_from_payload(payload),
            )
        )
    except Exception as exc:
        return _error_response(str(exc), 400)


async def save_auto_config(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        profile = service.get_profile(payload.get("profile_id"))
        if "auto_sync_enabled" in payload:
            profile.auto_sync_enabled = bool(payload["auto_sync_enabled"])
        if "interval_hours" in payload:
            profile.interval_hours = int(payload["interval_hours"])
        if "auto_resolve_enabled" in payload:
            profile.auto_resolve_enabled = bool(payload["auto_resolve_enabled"])
        service.save_profile(profile)
        return JSONResponse(profile.model_dump(mode="json"))
    except Exception as exc:
        return _error_response(str(exc), 400)


async def run_auto_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        return JSONResponse(
            await service.auto_sync(
                payload.get("profile_id"),
                shibboleth=_shibboleth_from_payload(payload),
            )
        )
    except Exception as exc:
        return _error_response(str(exc), 400)


async def unlock_shibboleth(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        shibboleth = _shibboleth_from_payload(payload)
        if not shibboleth:
            return _error_response("Shibboleth (passphrase) is required", 400)
        service = _service(request)
        profile = service.get_profile(payload.get("profile_id"))
        service.unlock_shibboleth(profile, shibboleth)
        return JSONResponse(
            {
                "success": True,
                "shibboleth_unlocked": True,
                "profile_id": profile.id,
            }
        )
    except Exception as exc:
        return _error_response(str(exc), 400)


async def lock_shibboleth(request: Request) -> JSONResponse:
    payload = await _json_payload(request)
    _service(request).lock_shibboleth(payload.get("profile_id"))
    return JSONResponse({"success": True, "shibboleth_unlocked": False})


async def resolve_conflicts_agent(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        profile = service.get_profile(payload.get("profile_id"))
        conflict = SyncConflict.model_validate(
            {
                "conflicting_paths": payload.get("conflicting_paths", []),
                "status": "resolving",
                "resolution_mode": "agent",
            }
        )
        result = await service.conflict_resolver.resolve_preview(
            conflict, Path(profile.repo_path) / PAYLOAD_DIR_NAME
        )
        return JSONResponse(result.model_dump(mode="json"))
    except Exception as exc:
        return _error_response(str(exc), 400)


async def stop_conflict_resolution(request: Request) -> JSONResponse:
    return JSONResponse(_service(request).stop_conflict_resolution())


async def apply_manual_conflict(request: Request) -> JSONResponse:
    return _error_response("Manual conflict apply is not yet implemented", 501)


async def enable_secret_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        shibboleth = _shibboleth_from_payload(payload)
        if not shibboleth:
            return _error_response(
                "Shibboleth (passphrase) is required to enable encrypted API key sync",
                400,
            )
        service = _service(request)
        profile = service.get_profile(payload.get("profile_id"))
        service.unlock_shibboleth(profile, shibboleth)
        profile.encrypted_secret_sync_enabled = True
        service.save_profile(profile)
        return JSONResponse(profile.model_dump(mode="json"))
    except Exception as exc:
        return _error_response(str(exc), 400)


async def disable_secret_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        profile = service.get_profile(payload.get("profile_id"))
        profile.encrypted_secret_sync_enabled = False
        service.save_profile(profile)
        service.lock_shibboleth(profile.id)
        return JSONResponse(profile.model_dump(mode="json"))
    except Exception as exc:
        return _error_response(str(exc), 400)


async def _json_payload(request: Request) -> dict:
    try:
        payload = await request.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _shibboleth_from_payload(payload: dict) -> str | None:
    value = payload.get("shibboleth")
    if isinstance(value, str) and value:
        return value
    return None


def _profile_from_payload(service: GitHubSyncService, payload: dict) -> SyncProfile:
    if "repo_path" in payload:
        return SyncProfile.model_validate(payload)
    if "repo" in payload:
        payload = {**payload, "repo_path": str(Path(payload["repo"]))}
        return SyncProfile.model_validate(payload)
    return service.get_profile(payload.get("profile_id"))


def _error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)
