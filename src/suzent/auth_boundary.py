"""
Network auth boundary for the Suzent server.

The app assumes loopback-only access by default (the desktop UI talks to it over
127.0.0.1). Once the server is exposed on the LAN/Tailscale (node_lan_bind), the
whole HTTP API would otherwise be reachable unauthenticated. This middleware
closes that hole:

- Requests from loopback are trusted (the local app) and pass through.
- Requests from any other address must present a valid node token
  (a durable per-device token, or the shared secret when node_auth_mode=token).
- The node WebSocket handshake (/ws/node) is exempt: it authenticates itself in
  the connect message.

The helpers are split out from the middleware so they can be unit-tested without
constructing an ASGI scope.
"""

from __future__ import annotations

import hmac

from starlette.responses import JSONResponse

# Hosts treated as the trusted local machine. Empty string and "testclient"
# cover in-process ASGI transports (Starlette TestClient) — a real network peer
# address is filled by the server and can't be spoofed to these values.
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "", "testclient"}

# Paths reachable from remote without a token (they self-authenticate).
_WS_EXEMPT_PATHS = {"/ws/node"}

# HTTP bootstrap paths reachable from remote without a token. These issue no
# secret — they only queue a control request an operator must approve, and the
# requester polls with an unguessable request_id. See node_routes.grant_request.
_HTTP_EXEMPT_PREFIXES = ("/nodes/grant-request", "/nodes/grant-status/")


def is_http_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _HTTP_EXEMPT_PREFIXES)


def is_loopback(host: str | None) -> bool:
    return (host or "") in LOOPBACK_HOSTS


def extract_token(headers: list[tuple[bytes, bytes]]) -> str:
    """Pull a bearer token from Authorization or X-Suzent-Token headers."""
    lookup = {k.lower(): v for k, v in (headers or [])}
    auth = lookup.get(b"authorization", b"").decode("latin-1")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return lookup.get(b"x-suzent-token", b"").decode("latin-1").strip()


def token_authorized(
    token: str,
    device_store,
    node_auth_mode: str,
    node_auth_token: str,
) -> bool:
    """True if the token is a known device token or the shared secret."""
    if not token:
        return False
    try:
        if device_store is not None and device_store.verify(token):
            return True
    except Exception:
        pass
    if (
        (node_auth_mode or "").lower() == "token"
        and node_auth_token
        and hmac.compare_digest(token, node_auth_token)
    ):
        return True
    return False


class AuthBoundaryMiddleware:
    """ASGI middleware enforcing the loopback-trusted / remote-token-required rule."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        client = scope.get("client")
        host = client[0] if client else ""
        if is_loopback(host):
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        # The node WebSocket authenticates itself in its handshake.
        if scope["type"] == "websocket" and path in _WS_EXEMPT_PATHS:
            return await self.app(scope, receive, send)
        # HTTP bootstrap endpoints (issue no secret; operator-gated).
        if scope["type"] == "http" and is_http_exempt(path):
            return await self.app(scope, receive, send)

        if self._authorized(scope):
            return await self.app(scope, receive, send)

        if scope["type"] == "http":
            resp = JSONResponse(
                {"error": "Unauthorized: remote access requires a valid node token"},
                status_code=401,
            )
            return await resp(scope, receive, send)
        # websocket
        await send({"type": "websocket.close", "code": 1008})

    def _authorized(self, scope) -> bool:
        from suzent.config import CONFIG

        token = extract_token(scope.get("headers", []))
        device_store = None
        app = scope.get("app")
        nm = getattr(getattr(app, "state", None), "node_manager", None)
        if nm is not None:
            device_store = getattr(nm, "device_store", None)
        return token_authorized(
            token,
            device_store,
            getattr(CONFIG, "node_auth_mode", "open"),
            getattr(CONFIG, "node_auth_token", "") or "",
        )
