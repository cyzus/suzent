"""
A2A auth wiring: the card is public, the RPC surface is not.

Publishing an Agent Card advertises that this device exists; it must never imply
authorization. These tests pin that split at the boundary layer, where remote
callers are actually gated.
"""

from types import SimpleNamespace

from suzent.auth_boundary import (
    AuthBoundaryMiddleware,
    agent_path_allowed,
    is_http_exempt,
    scope_allows,
)
from suzent.nodes.device_store import DeviceTokenStore


def test_agent_card_is_publicly_reachable():
    """Discovery only works if the card needs no token."""
    assert is_http_exempt("/.well-known/agent-card.json")


def test_rpc_surface_is_not_public():
    assert not is_http_exempt("/a2a/v1")


def test_agent_scope_may_drive_a2a_but_not_the_host():
    assert agent_path_allowed("/a2a/v1")
    assert scope_allows("agent", "/a2a/v1")
    # An A2A caller is still confined to the agent surface.
    assert not scope_allows("agent", "/config")
    assert not scope_allows("agent", "/a2a/status")


def test_node_scope_cannot_reach_a2a():
    """`node` tokens are for the WS handshake only — no HTTP surface at all."""
    assert not scope_allows("node", "/a2a/v1")


def test_unauthenticated_remote_caller_is_rejected(tmp_path):
    """A remote POST to /a2a/v1 with no token never reaches the route."""
    store = DeviceTokenStore(path=tmp_path / "devices.json")
    reached = False

    async def _app(scope, receive, send):
        nonlocal reached
        reached = True

    middleware = AuthBoundaryMiddleware(_app)
    scope = {
        "type": "http",
        "path": "/a2a/v1",
        "client": ("100.64.0.9", 51234),
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(node_manager=SimpleNamespace(device_store=store))
        ),
    }

    sent = []

    async def _send(message):
        sent.append(message)

    async def _receive():
        return {"type": "http.request", "body": b""}

    import asyncio

    asyncio.run(middleware(scope, _receive, _send))

    assert not reached
    assert sent[0]["status"] == 401


def test_granted_remote_caller_reaches_the_route(tmp_path):
    """A device grant minted by the pairing flow is what authorizes A2A."""
    store = DeviceTokenStore(path=tmp_path / "devices.json")
    _device_id, token = store.mint("Research Bot", "linux", scope="agent")
    reached = False

    async def _app(scope, receive, send):
        nonlocal reached
        reached = True

    middleware = AuthBoundaryMiddleware(_app)
    scope = {
        "type": "http",
        "path": "/a2a/v1",
        "client": ("100.64.0.9", 51234),
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "app": SimpleNamespace(
            state=SimpleNamespace(node_manager=SimpleNamespace(device_store=store))
        ),
    }

    async def _send(message):
        pass

    async def _receive():
        return {"type": "http.request", "body": b""}

    import asyncio

    asyncio.run(middleware(scope, _receive, _send))

    assert reached
