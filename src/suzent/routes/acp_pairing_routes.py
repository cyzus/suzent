"""Local operator approval and credential verification for inbound ACP clients."""

from pydantic import BaseModel, Field, StrictBool, ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from suzent.acp.pairing import ACPPairingStore
from suzent.auth_boundary import extract_token, host_header_is_local, is_loopback
from suzent.config import USER_CONFIG_DIR


class PairRequest(BaseModel):
    client_name: str = Field(
        min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$"
    )


class DecisionRequest(BaseModel):
    approved: StrictBool


def require_local_operator(request: Request) -> None:
    # These routes are local-only even when a remote caller holds a host token.
    if (
        not request.client
        or not is_loopback(request.client.host)
        or not host_header_is_local(request.headers.get("host", ""))
    ):
        raise HTTPException(403, "ACP pairing requires the local Suzent backend")
    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit

        parsed = urlsplit(origin)
        trusted = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and host_header_is_local(parsed.netloc)
        )
        if (
            origin
            not in {
                "tauri://localhost",
                "http://tauri.localhost",
                "https://tauri.localhost",
            }
            and not trusted
        ):
            raise HTTPException(403, "Untrusted pairing origin")


def store(request: Request) -> ACPPairingStore:
    require_local_operator(request)
    if not hasattr(request.app.state, "acp_pairing"):
        request.app.state.acp_pairing = ACPPairingStore(
            USER_CONFIG_DIR / "acp_grants.json"
        )
    return request.app.state.acp_pairing


def token(request: Request) -> str:
    value = extract_token(request.headers.raw)
    if len(value) < 40 or len(value) > 256:
        raise HTTPException(401, "ACP credential required")
    return value


def reply(value: object, status: int = 200) -> JSONResponse:
    return JSONResponse(
        value, status_code=status, headers={"Cache-Control": "no-store"}
    )


async def begin(request: Request) -> JSONResponse:
    try:
        body = PairRequest.model_validate(await request.json())
        return reply(store(request).begin(body.client_name, token(request)), 201)
    except (ValueError, ValidationError):
        return reply({"error": "Invalid or unavailable ACP pairing request"}, 400)


async def collect(request: Request) -> JSONResponse:
    try:
        return reply(
            store(request).collect(request.path_params["request_id"], token(request))
        )
    except ValueError:
        return reply({"error": "ACP request unavailable, expired, or revoked"}, 400)


async def cancel(request: Request) -> JSONResponse:
    try:
        store(request).cancel(request.path_params["request_id"], token(request))
        return reply({"ok": True})
    except ValueError:
        return reply({"error": "ACP request unavailable"}, 400)


async def status(request: Request) -> JSONResponse:
    pairing = store(request)
    return reply({"pending": pairing.pending(), "grants": pairing.grants()})


async def decide(request: Request) -> JSONResponse:
    try:
        body = DecisionRequest.model_validate(await request.json())
        store(request).decide(request.path_params["request_id"], body.approved)
        return reply({"ok": True})
    except (ValueError, ValidationError):
        return reply({"error": "ACP request unavailable or invalid decision"}, 400)


async def revoke(request: Request) -> JSONResponse:
    store(request).revoke(request.path_params["grant_id"])
    return reply({"ok": True})


async def verify(request: Request) -> JSONResponse:
    grant = store(request).verify(token(request))
    if grant is None:
        return reply({"error": "ACP authorization required"}, 401)
    return reply({"authenticated": True, "grant_id": grant.grant_id})


acp_pairing_routes = [
    Route("/acp/auth/pair", begin, methods=["POST"]),
    Route("/acp/auth/requests/{request_id}/collect", collect, methods=["POST"]),
    Route("/acp/auth/requests/{request_id}/cancel", cancel, methods=["POST"]),
    Route("/acp/auth/requests/{request_id}/decide", decide, methods=["POST"]),
    Route("/acp/auth/status", status, methods=["GET"]),
    Route("/acp/auth/grants/{grant_id}", revoke, methods=["DELETE"]),
    Route("/acp/auth/verify", verify, methods=["POST"]),
]
