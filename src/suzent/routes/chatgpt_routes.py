from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.logger import get_logger

logger = get_logger(__name__)


def _authenticator():
    from litellm.llms.chatgpt.authenticator import Authenticator

    return Authenticator()


def _status_payload(auth) -> dict[str, Any]:
    data = auth._read_auth_file()
    if not data:
        return {"connected": False, "status": "not_logged_in"}

    token = data.get("access_token")
    if not token:
        return {"connected": False, "status": "not_logged_in"}

    if auth._is_token_expired(data, token):
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            return {"connected": False, "status": "token_expired"}
        try:
            auth._refresh_tokens(refresh_token)
            return {
                "connected": True,
                "status": "connected",
                "account_id": auth.get_account_id(),
            }
        except Exception:
            return {"connected": False, "status": "token_expired"}

    return {
        "connected": True,
        "status": "connected",
        "account_id": auth.get_account_id(),
        "auth_file": auth.auth_file,
    }


async def get_chatgpt_status(request: Request) -> JSONResponse:
    auth = _authenticator()
    payload = await asyncio.to_thread(_status_payload, auth)
    return JSONResponse(payload)


async def start_chatgpt_login(request: Request) -> JSONResponse:
    """Request a device code and immediately start blocking poll in a background thread.

    Returns the verify_url and user_code for the frontend to display while waiting.
    The frontend then polls GET /chatgpt/status to detect completion.
    """
    auth = _authenticator()

    def _begin():
        from litellm.llms.chatgpt.common_utils import GetDeviceCodeError

        try:
            device_code = auth._request_device_code()
            auth._record_device_code_request()
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
            auth_code = auth._poll_for_authorization_code(dc)
            tokens = auth._exchange_code_for_tokens(auth_code)
            auth._write_auth_file(auth._build_auth_record(tokens))
            logger.info("ChatGPT device-code login completed")
        except Exception as exc:
            logger.warning("ChatGPT device-code login failed: {}", exc)

    asyncio.get_event_loop().run_in_executor(None, _complete_login)

    from litellm.llms.chatgpt.common_utils import CHATGPT_DEVICE_VERIFY_URL

    return JSONResponse(
        {
            "success": True,
            "verify_url": CHATGPT_DEVICE_VERIFY_URL,
            "user_code": dc["user_code"],
            "device_auth_id": dc["device_auth_id"],
            "interval": dc.get("interval", "5"),
        }
    )


async def logout_chatgpt(request: Request) -> JSONResponse:
    auth = _authenticator()

    def _logout():
        from pathlib import Path

        try:
            Path(auth.auth_file).unlink(missing_ok=True)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    result = await asyncio.to_thread(_logout)
    return JSONResponse(result, status_code=200 if result["success"] else 500)
