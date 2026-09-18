"""Mobile pairing endpoints. Operator routes require host authorization."""

import socket
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from suzent.config import USER_CONFIG_DIR
from suzent.mobile.pairing import ClientPermissions, PairingError, PairingStore


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permissions: ClientPermissions | None = None


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairing_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairing_id: str = Field(min_length=32, max_length=32)
    invitation: str = Field(min_length=40, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    platform: Literal["ios", "android"]
    confirm_permissions: StrictBool = False
    rotate: StrictBool = False
    repair_proof: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class PickupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairing_id: str = Field(min_length=32, max_length=32)
    pickup_secret: str = Field(min_length=40, max_length=64)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permissions: ClientPermissions | None = None


def get_mobile_store(request: Request) -> PairingStore:
    state = request.app.state
    if not hasattr(state, "mobile_store"):
        try:
            state.mobile_store = PairingStore(USER_CONFIG_DIR / "mobile_clients.json")
        except (OSError, ValueError, TypeError):
            raise HTTPException(503, "Mobile authorization store unavailable") from None
    return state.mobile_store


def reply(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


async def capabilities(request: Request) -> JSONResponse:
    return reply(
        {
            "client_protocol": 1,
            "stream_protocols": [1],
            "pairing_protocol": 1,
            "pairing_repair": 1,
        }
    )


async def invite(request: Request) -> JSONResponse:
    try:
        body = InviteRequest.model_validate(await request.json())
        return reply(
            get_mobile_store(request).invite(
                body.permissions, socket.gethostname()[:100]
            ),
            201,
        )
    except PairingError:
        return reply({"error": "Too many pending invitations"}, 429)
    except (ValidationError, ValueError):
        return reply({"error": "Invalid invitation permissions"}, 400)


async def preview(request: Request) -> JSONResponse:
    try:
        body = PreviewRequest.model_validate(await request.json())
        return reply(get_mobile_store(request).preview(body.pairing_id))
    except (ValidationError, ValueError):
        return reply({"error": "Invitation unavailable or invalid"}, 400)


async def cancel(request: Request) -> JSONResponse:
    return reply(
        {"ok": get_mobile_store(request).cancel(request.path_params["pairing_id"])}
    )


async def claim(request: Request) -> JSONResponse:
    try:
        body = ClaimRequest.model_validate(await request.json())
        return reply(get_mobile_store(request).claim(**body.model_dump()))
    except (ValidationError, ValueError):
        return reply({"error": "Invitation unavailable or invalid"}, 400)


async def collect(request: Request) -> JSONResponse:
    try:
        body = PickupRequest.model_validate(await request.json())
        return reply(get_mobile_store(request).collect(**body.model_dump()))
    except (ValidationError, ValueError):
        return reply({"error": "Pairing unavailable or invalid"}, 400)


async def pending(request: Request) -> JSONResponse:
    return reply({"pending": get_mobile_store(request).pending()})


async def decide(request: Request) -> JSONResponse:
    try:
        body = DecisionRequest.model_validate(await request.json())
        get_mobile_store(request).decide(
            request.path_params["pairing_id"], body.permissions
        )
        return reply({"ok": True})
    except (ValidationError, ValueError):
        return reply({"error": "Pairing unavailable or invalid"}, 400)


async def devices(request: Request) -> JSONResponse:
    return reply({"devices": get_mobile_store(request).devices()})


async def revoke(request: Request) -> JSONResponse:
    removed = get_mobile_store(request).revoke(request.path_params["device_id"])
    return reply({"ok": removed}, 200 if removed else 404)


mobile_routes = [
    Route("/mobile/capabilities", capabilities, methods=["GET"]),
    Route("/mobile/pairing/invite", invite, methods=["POST"]),
    Route("/mobile/pairing/claim", claim, methods=["POST"]),
    Route("/mobile/pairing/preview", preview, methods=["POST"]),
    Route("/mobile/pairing/{pairing_id}/cancel", cancel, methods=["POST"]),
    Route("/mobile/pairing/collect", collect, methods=["POST"]),
    Route("/mobile/pairing/pending", pending, methods=["GET"]),
    Route("/mobile/pairing/{pairing_id}/decide", decide, methods=["POST"]),
    Route("/mobile/devices", devices, methods=["GET"]),
    Route("/mobile/devices/{device_id}/revoke", revoke, methods=["POST"]),
]
