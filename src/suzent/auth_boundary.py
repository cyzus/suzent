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
_HTTP_EXEMPT_PREFIXES = (
    "/nodes/grant-request",
    "/nodes/grant-status/",
    "/channels/suzent/grant-changed",  # untrusted revoke hint; receiver re-verifies
)


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


# Routes a remote "agent"-scope token (a control grant) may reach — just enough
# to trigger this device's agent and complete the mutual handshake. Everything
# else (config, sandbox, devices, …) requires a "full"-scope (host) token or
# loopback.
#   /chat, /chat/stop  → trigger / stop the agent
#   /nodes/peer-offer  → the peer offers us a reverse grant (mutual setup);
#                        it only adds a peer record, can't read or change ours.
AGENT_ALLOWED_PATHS = {
    "/chat",
    "/chat/stop",
    "/nodes/peer-offer",
    "/nodes/peer-invoke",  # run a local capability on behalf of a controller
    "/channels/suzent/inbound",  # peer agent-to-agent messages
    "/channels/suzent/whoami",  # peer token-validity self-check
}


def token_scope(token: str, device_store) -> str | None:
    """Return the scope of a token (node | agent | full), or None if invalid."""
    if not token or device_store is None:
        return None
    try:
        rec = device_store.verify(token)
    except Exception:
        rec = None
    if not rec:
        return None
    return rec.get("scope", "node")


def scope_allows(scope: str | None, path: str) -> bool:
    """Whether a token scope may reach an HTTP path (remote caller)."""
    if scope == "full":
        return True
    if scope == "agent":
        return path in AGENT_ALLOWED_PATHS
    # "node" tokens are for the WS handshake only; no HTTP surface.
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

        tok_scope = self._token_scope(scope)
        if tok_scope is None:
            # No/invalid token.
            if scope["type"] == "http":
                resp = JSONResponse(
                    {"error": "Unauthorized: remote access requires a node token"},
                    status_code=401,
                )
                return await resp(scope, receive, send)
            await send({"type": "websocket.close", "code": 1008})
            return

        if scope["type"] == "websocket" or scope_allows(tok_scope, path):
            return await self.app(scope, receive, send)

        # Valid token, but its scope doesn't cover this route.
        resp = JSONResponse(
            {
                "error": (
                    f"Forbidden: this token's scope ('{tok_scope}') can't access "
                    f"{path}. A host-scope token is required for full access."
                )
            },
            status_code=403,
        )
        return await resp(scope, receive, send)

    def _token_scope(self, scope) -> str | None:
        token = extract_token(scope.get("headers", []))
        app = scope.get("app")
        nm = getattr(getattr(app, "state", None), "node_manager", None)
        device_store = getattr(nm, "device_store", None) if nm is not None else None
        return token_scope(token, device_store)
