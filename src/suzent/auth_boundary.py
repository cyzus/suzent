"""
Network auth boundary for the Suzent server.

The app assumes loopback-only access by default (the desktop UI talks to it over
127.0.0.1). Once the server is exposed on the LAN/Tailscale (node_lan_bind), the
whole HTTP API would otherwise be reachable unauthenticated. This middleware
closes that hole:

- Requests from loopback are trusted (the local app) and pass through.
- Requests from any other address must present a valid durable per-device
  token (minted when an operator approves the device).
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
    # The route validates either a durable device grant or its own short-lived,
    # artifact-specific bearer. This exception lets a one-way peer present the
    # latter without requiring a permanent reverse grant.
    "/nodes/peer-files/",
    # A2A discovery. The card is a public document by design — that is what
    # makes an agent discoverable — and the route itself 404s unless the
    # operator opted in. It authorizes nothing: /a2a/v1 still needs a grant.
    "/.well-known/agent-card.json",
)


# Exempt by EXACT path only. These must never be prefixes: "/node" as a prefix
# would also match "/nodes/devices" and "/nodes/pending/{code}/approve", handing
# the entire device API to unauthenticated remote callers.
_HTTP_EXEMPT_PATHS = {
    # The browser-node page. A device joining the mesh has no token yet, so the
    # page must be fetchable without one. It is static markup carrying no
    # secrets; the /ws/node handshake it then performs still requires approval.
    "/node",
}


def is_http_exempt(path: str) -> bool:
    return path in _HTTP_EXEMPT_PATHS or any(
        path.startswith(p) for p in _HTTP_EXEMPT_PREFIXES
    )


def is_loopback(host: str | None) -> bool:
    return (host or "") in LOOPBACK_HOSTS


# Host names a loopback client may address us by. A browser reaching
# 127.0.0.1 through a rebound DNS name is same-origin with the attacker's page,
# so CORS never runs — the Host header is the only thing that still tells the
# two apart. Names an operator legitimately fronts us with (a reverse proxy on
# the same machine) go in SUZENT_ALLOWED_HOSTS, comma-separated.
# "testserver" is the Host that Starlette's in-process TestClient sends; it
# never appears on a real network.
LOOPBACK_HOST_NAMES = {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}


def extra_allowed_hosts() -> set[str]:
    import os

    return {
        h.strip().lower()
        for h in os.getenv("SUZENT_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    }


def host_header_allowed(host_header: str) -> bool:
    """Whether a loopback client's Host header names this server legitimately."""
    if not host_header:
        # HTTP/1.0 and some local probes send none; there is no rebinding
        # without a name, so nothing to defend against.
        return True
    name = host_header.strip().lower()
    # Strip the port, keeping IPv6 brackets intact.
    if name.startswith("["):
        name = name.split("]")[0] + "]"
    elif ":" in name:
        name = name.rsplit(":", 1)[0]
    return name in LOOPBACK_HOST_NAMES or name in extra_allowed_hosts()


def extract_token(headers: list[tuple[bytes, bytes]]) -> str:
    """Pull a bearer token from Authorization or X-Suzent-Token headers."""
    lookup = {k.lower(): v for k, v in (headers or [])}
    auth = lookup.get(b"authorization", b"").decode("latin-1")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return lookup.get(b"x-suzent-token", b"").decode("latin-1").strip()


# Paths that may carry their token in the query string instead of a header.
#
# Deliberately tiny: a query token lands in access logs, Referer headers and
# browser history, so it is only worth it where a header is impossible. The
# browser's `EventSource` is exactly that case — it cannot set request headers,
# and these two endpoints are how the web UI receives everything the agent does.
# Both are read-only GET streams.
QUERY_TOKEN_PATHS = {"/events/stream", "/subagents/stream"}


def extract_query_token(path: str, query_string: bytes | str) -> str:
    """Pull a token from the query string, for the few paths that allow it."""
    if path not in QUERY_TOKEN_PATHS:
        return ""
    from urllib.parse import parse_qs

    raw = (
        query_string.decode("latin-1")
        if isinstance(query_string, bytes)
        else (query_string or "")
    )
    values = parse_qs(raw).get("token") or []
    return values[0].strip() if values else ""


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
    "/nodes",  # read-only: a controller may list our nodes' capabilities
    "/nodes/peer-offer",
    "/nodes/peer-invoke",  # run a local capability on behalf of a controller
    "/channels/suzent/inbound",  # peer agent-to-agent messages
    "/channels/suzent/inbox",  # durable peer agent-to-agent messages
    "/channels/suzent/session",  # peer-owned session transcript
    "/channels/suzent/stop",  # stop the peer-owned session
    "/channels/suzent/whoami",  # peer token-validity self-check
    "/a2a/v1",  # A2A JSON-RPC: send/stream messages, get/cancel tasks
}

AGENT_ALLOWED_PREFIXES = ("/nodes/peer-files/",)


def agent_path_allowed(path: str) -> bool:
    return path in AGENT_ALLOWED_PATHS or any(
        path.startswith(prefix) for prefix in AGENT_ALLOWED_PREFIXES
    )


def token_scope(token: str, device_store) -> str | None:
    """Return the scope of a token (node | agent | full), or None if invalid.

    A grant whose status is ``paused`` is treated as invalid (returns None), so
    the holder is denied without the durable token being revoked.
    """
    if not token or device_store is None:
        return None
    try:
        rec = device_store.verify(token)
    except Exception:
        rec = None
    if not rec:
        return None
    if rec.get("status", "active") != "active":
        return None
    return rec.get("scope", "node")


def scope_allows(scope: str | None, path: str) -> bool:
    """Whether a token scope may reach an HTTP path (remote caller)."""
    if scope == "full":
        return True
    if scope == "agent":
        return agent_path_allowed(path)
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
            headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
            host_header = headers.get(b"host", b"").decode("latin-1")
            if not host_header_allowed(host_header):
                resp = JSONResponse(
                    {"error": f"Unrecognized Host header: {host_header}"},
                    status_code=421,
                )
                return await resp(scope, receive, send)
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        # The node WebSocket authenticates itself in its handshake.
        if scope["type"] == "websocket" and path in _WS_EXEMPT_PATHS:
            return await self.app(scope, receive, send)
        # HTTP bootstrap endpoints (issue no secret; operator-gated).
        if scope["type"] == "http" and is_http_exempt(path):
            return await self.app(scope, receive, send)
        # The web UI's own static shell. Imported lazily so the auth boundary
        # stays importable (and unit-testable) without the server package.
        if scope["type"] == "http":
            from suzent.webui import is_public_asset

            if is_public_asset(path):
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
        token = extract_token(scope.get("headers", [])) or extract_query_token(
            scope.get("path", ""), scope.get("query_string", b"")
        )
        app = scope.get("app")
        nm = getattr(getattr(app, "state", None), "node_manager", None)
        device_store = getattr(nm, "device_store", None) if nm is not None else None
        return token_scope(token, device_store)
