from __future__ import annotations

import secrets
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.sync.github_api import (
    GitHubApiError,
    clear_github_token,
    get_authenticated_user,
    github_token_expired_without_refresh,
    resolve_github_token,
    store_github_token,
)
from suzent.sync.github_device_flow import (
    DeviceFlowDenied,
    DeviceFlowExpired,
    DeviceFlowState,
    poll,
    start,
)
from suzent.sync.models import SyncProfile
from suzent.sync.service import DestructiveSyncPlanError, GitHubSyncService

_SESSION_TTL = 900

_device_sessions: dict[str, DeviceFlowState] = {}


def _prune_sessions() -> None:
    now = time.monotonic()
    stale = [
        k for k, s in _device_sessions.items() if now - s.started_at > _SESSION_TTL
    ]
    for k in stale:
        del _device_sessions[k]


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
                repo_path=payload.get("repo_path"),
                branch=payload.get("branch"),
                remote=payload.get("remote"),
                auto_sync_enabled=bool(payload.get("auto_sync_enabled", True)),
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


async def get_sync_plan(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        operation = payload.get("operation")
        profile_id = payload.get("profile_id")
        plan = await _service(request).preview_sync_plan_safe(
            str(operation),
            profile_id,
            refresh_remote=bool(payload.get("refresh_remote", True)),
        )
        return JSONResponse(plan.model_dump(mode="json"))
    except Exception as exc:
        return _error_response(str(exc), 400)


async def get_sync_file_diff(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        path = str(payload.get("path") or "")
        direction = str(payload.get("direction") or "")
        diff = await _service(request).preview_file_diff_safe(
            path,
            direction,
            payload.get("profile_id"),
        )
        return JSONResponse({"path": path, "diff": diff})
    except Exception as exc:
        return _error_response(str(exc), 400)


async def pull_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        return JSONResponse(
            await service.pull(
                payload.get("profile_id"),
                confirm_destructive=bool(payload.get("confirm_destructive")),
                prefer_cloud=bool(payload.get("prefer_cloud")),
            )
        )
    except DestructiveSyncPlanError as exc:
        return JSONResponse(
            {
                "detail": str(exc),
                "review_required": True,
                "plan": exc.plan.model_dump(mode="json"),
            },
            status_code=409,
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
                confirm_destructive=bool(payload.get("confirm_destructive")),
            )
        )
    except DestructiveSyncPlanError as exc:
        return JSONResponse(
            {
                "detail": str(exc),
                "review_required": True,
                "plan": exc.plan.model_dump(mode="json"),
            },
            status_code=409,
        )
    except Exception as exc:
        return _error_response(str(exc), 400)


async def discard_outgoing_sync(request: Request) -> JSONResponse:
    try:
        payload = await _json_payload(request)
        service = _service(request)
        paths = payload.get("paths")
        return JSONResponse(
            await service.discard_outgoing(
                payload.get("profile_id"),
                paths=[str(path) for path in paths]
                if isinstance(paths, list)
                else None,
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
                confirm_destructive=bool(payload.get("confirm_destructive")),
            )
        )
    except Exception as exc:
        return _error_response(str(exc), 400)


async def start_github_auth(request: Request) -> JSONResponse:
    _prune_sessions()
    try:
        state = start()
    except Exception as exc:
        return _error_response(str(exc), 502)
    session_id = secrets.token_urlsafe(16)
    _device_sessions[session_id] = state
    return JSONResponse(
        {
            "session_id": session_id,
            "user_code": state.user_code,
            "verification_uri": state.verification_uri,
            "expires_in": state.expires_in,
            "interval": state.interval,
        }
    )


async def poll_github_auth(request: Request) -> JSONResponse:
    payload = await _json_payload(request)
    session_id = payload.get("session_id", "")
    state = _device_sessions.get(session_id)
    if state is None:
        return _error_response("Unknown or expired auth session", 404)
    try:
        token = poll(state)
    except DeviceFlowExpired:
        _device_sessions.pop(session_id, None)
        return JSONResponse({"status": "expired"})
    except DeviceFlowDenied:
        _device_sessions.pop(session_id, None)
        return JSONResponse({"status": "denied"})
    except Exception as exc:
        return _error_response(str(exc), 502)

    if token:
        store_github_token(
            token.access_token,
            expires_in=token.expires_in,
            refresh_token=token.refresh_token,
            refresh_token_expires_in=token.refresh_token_expires_in,
            token_type=token.token_type,
            scope=token.scope,
        )
        _device_sessions.pop(session_id, None)
        username = None
        try:
            username = get_authenticated_user(token.access_token)
        except Exception:
            pass
        return JSONResponse(
            {"status": "complete", "username": username, "interval": state.interval}
        )
    return JSONResponse({"status": "pending", "interval": state.interval})


async def get_github_auth_status(request: Request) -> JSONResponse:
    token = resolve_github_token()
    if not token:
        if github_token_expired_without_refresh():
            return JSONResponse(
                {"authenticated": False, "username": None, "token_expired": True}
            )
        return JSONResponse({"authenticated": False, "username": None})
    try:
        username = get_authenticated_user(token)
        return JSONResponse({"authenticated": True, "username": username})
    except GitHubApiError as exc:
        # Only treat 401 as an actual expiry; other API errors leave auth state unknown
        if "401" in str(exc):
            return JSONResponse(
                {"authenticated": False, "username": None, "token_expired": True}
            )
        return JSONResponse({"authenticated": True, "username": None})
    except Exception:
        # Network/timeout — token likely still valid, don't force re-login
        return JSONResponse({"authenticated": True, "username": None})


async def logout_github_auth(request: Request) -> JSONResponse:
    clear_github_token()
    return JSONResponse({"success": True})


async def _json_payload(request: Request) -> dict:
    try:
        payload = await request.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _profile_from_payload(service: GitHubSyncService, payload: dict) -> SyncProfile:
    if "repo_path" in payload:
        return SyncProfile.model_validate(payload)
    if "repo" in payload:
        payload = {**payload, "repo_path": str(Path(payload["repo"]))}
        return SyncProfile.model_validate(payload)
    return service.get_profile(payload.get("profile_id"))


def _error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)
