"""
WeChat social-channel authentication routes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.channels.wechat import DEFAULT_BASE_URL, WeChatAuthClient, WeChatQrLogin
from suzent.logger import logger


LOGIN_TTL_SECONDS = 300


@dataclass
class WeChatLoginSession:
    id: str
    base_url: str
    login: WeChatQrLogin
    created_at: float
    updated_at: float
    status: str = "pending"


_sessions: dict[str, WeChatLoginSession] = {}


def _cleanup_sessions() -> None:
    now = time.time()
    expired = [
        session_id
        for session_id, session in _sessions.items()
        if now - session.created_at > LOGIN_TTL_SECONDS
        or session.status in {"confirmed", "expired", "cancelled"}
    ]
    for session_id in expired:
        _sessions.pop(session_id, None)


def _session_payload(session: WeChatLoginSession) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "status": session.status,
        "qrcode": session.login.qrcode,
        "qrcode_img_content": session.login.qrcode_img_content,
        "qrcode_url": session.login.qrcode_url,
        "base_url": session.base_url,
        "expires_at": session.created_at + LOGIN_TTL_SECONDS,
    }


async def start_wechat_login(request: Request) -> JSONResponse:
    """Create a WeChat QR login session for the settings UI."""
    _cleanup_sessions()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    base_url = str(payload.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        return JSONResponse({"error": "Invalid base_url"}, status_code=400)

    try:
        login = await WeChatAuthClient(base_url).create_qrcode()
    except Exception as exc:
        logger.warning("Failed to start WeChat QR login: {}", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)

    session_id = uuid.uuid4().hex
    session = WeChatLoginSession(
        id=session_id,
        base_url=base_url,
        login=login,
        created_at=time.time(),
        updated_at=time.time(),
    )
    _sessions[session_id] = session
    return JSONResponse(_session_payload(session))


async def poll_wechat_login(request: Request) -> JSONResponse:
    """Poll a WeChat QR login session until it is confirmed or expires."""
    _cleanup_sessions()
    session_id = request.path_params.get("session_id", "")
    session = _sessions.get(session_id)
    if session is None:
        return JSONResponse({"error": "Unknown or expired session"}, status_code=404)

    try:
        status = await WeChatAuthClient(session.base_url).get_qrcode_status(
            session.login.qrcode
        )
    except Exception as exc:
        logger.warning("Failed to poll WeChat QR login: {}", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)

    session.status = status.status
    session.updated_at = time.time()

    payload = _session_payload(session)
    if status.status == "confirmed" and status.bot_token:
        payload["bot_token"] = status.bot_token
        payload["base_url"] = status.base_url or session.base_url
        payload["authorized_user_id"] = status.user_id
        payload["bot_id"] = status.bot_id
        _sessions.pop(session_id, None)
    return JSONResponse(payload)
