from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger
from suzent.core.providers.chatgpt_auth import (
    ChatGPTAuthUnavailable,
    chatgpt_device_verify_url,
    complete_device_login,
    create_authenticator,
    delete_auth_file,
    get_account_id,
    get_valid_access_token,
    read_auth_file,
    request_device_code,
)

logger = get_logger(__name__)


def _authenticator():
    return create_authenticator()


def _status_payload(auth) -> dict[str, Any]:
    data = read_auth_file(auth)
    if not data:
        return {"connected": False, "status": "not_logged_in"}

    token = data.get("access_token")
    if not token:
        return {"connected": False, "status": "not_logged_in"}

    if not get_valid_access_token(auth):
        return {"connected": False, "status": "token_expired"}

    return {
        "connected": True,
        "status": "connected",
        "account_id": get_account_id(auth),
    }


async def get_chatgpt_status(request: Request) -> JSONResponse:
    try:
        auth = _authenticator()
        payload = await asyncio.to_thread(_status_payload, auth)
    except ChatGPTAuthUnavailable as exc:
        payload = {"connected": False, "status": "not_logged_in", "error": str(exc)}
    return JSONResponse(payload)


async def start_chatgpt_login(request: Request) -> JSONResponse:
    """Request a device code and immediately start blocking poll in a background thread.

    Returns the verify_url and user_code for the frontend to display while waiting.
    The frontend then polls GET /chatgpt/status to detect completion.
    """
    try:
        auth = _authenticator()
    except ChatGPTAuthUnavailable as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)

    def _begin():
        from litellm.llms.chatgpt.common_utils import GetDeviceCodeError

        try:
            device_code = request_device_code(auth)
            return {"success": True, "device_code": device_code}
        except GetDeviceCodeError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    result = await asyncio.to_thread(_begin)
    if not result["success"]:
        return JSONResponse(
            {"success": False, "error": result["error"]}, status_code=500
        )

    dc = result["device_code"]

    # Run the blocking poll+exchange in a fire-and-forget background thread.
    # The frontend polls GET /chatgpt/status to detect when auth completes.
    def _complete_login():
        try:
            complete_device_login(auth, dc)
            logger.info("ChatGPT device-code login completed")
        except Exception as exc:
            logger.warning("ChatGPT device-code login failed: {}", exc)

    asyncio.get_running_loop().run_in_executor(None, _complete_login)

    return JSONResponse(
        {
            "success": True,
            "verify_url": chatgpt_device_verify_url(),
            "user_code": dc["user_code"],
            "device_auth_id": dc["device_auth_id"],
            "interval": dc.get("interval", "5"),
        }
    )


async def logout_chatgpt(request: Request) -> JSONResponse:
    try:
        auth = _authenticator()
    except ChatGPTAuthUnavailable as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)

    def _logout():
        try:
            delete_auth_file(auth)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    result = await asyncio.to_thread(_logout)
    return JSONResponse(result, status_code=200 if result["success"] else 500)
