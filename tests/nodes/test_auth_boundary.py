"""
Tests for the network auth boundary: loopback is trusted, remote callers need a
valid node token, and the /ws/node handshake is exempt.
"""

from types import SimpleNamespace

import pytest

from suzent.auth_boundary import (
    AuthBoundaryMiddleware,
    agent_path_allowed,
    extract_token,
    is_http_exempt,
    is_loopback,
    scope_allows,
    token_scope,
)
from suzent.nodes.device_store import DeviceTokenStore


def test_is_loopback():
    assert is_loopback("127.0.0.1")
    assert is_loopback("::1")
    assert is_loopback("")  # in-process transport
    assert not is_loopback("100.64.0.5")
    assert not is_loopback("192.168.1.4")


def test_extract_token():
    assert extract_token([(b"authorization", b"Bearer abc123")]) == "abc123"
    assert extract_token([(b"Authorization", b"bearer xyz")]) == "xyz"
    assert extract_token([(b"x-suzent-token", b"tok")]) == "tok"
    assert extract_token([]) == ""


def test_token_scope(tmp_path):
    store = DeviceTokenStore(path=tmp_path / "d.json")
    _i, agent_tok = store.mint("Peer", "peer", scope="agent")
    _j, full_tok = store.mint("Host", "host", scope="full")
    _k, node_tok = store.mint("Phone", "ios", scope="node")

    assert token_scope(agent_tok, store) == "agent"
    assert token_scope(full_tok, store) == "full"
    assert token_scope(node_tok, store) == "node"
    assert token_scope("nope", store) is None
    assert token_scope("", store) is None


def test_scope_allows():
    # full → everything; agent → only the agent routes; node → nothing (HTTP).
    assert scope_allows("full", "/nodes/config")
    assert scope_allows("full", "/chat")
    assert scope_allows("agent", "/chat")
    assert scope_allows("agent", "/chat/stop")
    assert scope_allows("agent", "/nodes/peer-offer")  # mutual handshake
    assert scope_allows("agent", "/channels/suzent/inbox")
    assert scope_allows("agent", "/channels/suzent/session")
    assert scope_allows("agent", "/channels/suzent/stop")
    assert not scope_allows("agent", "/nodes/config")
    assert not scope_allows("agent", "/nodes/peers")
    assert not scope_allows("agent", "/sandbox/files")
    assert not scope_allows("node", "/chat")
    assert not scope_allows(None, "/chat")


def test_agent_path_allowed_peer_files_prefix_only():
    assert agent_path_allowed("/nodes/peer-files/pf_abc123")
    assert not agent_path_allowed("/nodes/peer-files")
    assert not agent_path_allowed("/sandbox/serve/chat/file.png")


def test_peer_file_route_accepts_self_authenticating_transfer_grants():
    assert is_http_exempt("/nodes/peer-files/pf_abc123")


# ─── Middleware behavior ─────────────────────────────────────────────


def _scope(scope_type, host, headers=None, path="/chat", store=None):
    app = SimpleNamespace(
        state=SimpleNamespace(node_manager=SimpleNamespace(device_store=store))
    )
    return {
        "type": scope_type,
        "client": (host, 5000),
        "headers": headers or [],
        "path": path,
        "app": app,
    }


async def _run(scope):
    """Run the middleware; return (inner_called, sent_messages)."""
    inner = {"called": False}

    async def app(scope, receive, send):
        inner["called"] = True

    sent = []

    async def send(m):
        sent.append(m)

    async def receive():
        return {"type": "http.request"}

    mw = AuthBoundaryMiddleware(app)
    await mw(scope, receive, send)
    return inner["called"], sent


class TestMiddleware:
    @pytest.mark.asyncio
    async def test_loopback_passes(self):
        called, _ = await _run(_scope("http", "127.0.0.1"))
        assert called

    @pytest.mark.asyncio
    async def test_remote_without_token_blocked(self):
        called, sent = await _run(_scope("http", "100.64.0.5"))
        assert not called
        assert sent and sent[0]["status"] == 401

    @pytest.mark.asyncio
    async def test_remote_agent_token_reaches_chat(self, tmp_path):
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Peer", "linux", scope="agent")
        scope = _scope(
            "http",
            "100.64.0.5",
            headers=[(b"authorization", f"Bearer {token}".encode())],
            path="/chat",
            store=store,
        )
        called, _ = await _run(scope)
        assert called

    @pytest.mark.asyncio
    async def test_remote_agent_token_blocked_on_other_routes(self, tmp_path):
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Peer", "linux", scope="agent")
        scope = _scope(
            "http",
            "100.64.0.5",
            headers=[(b"authorization", f"Bearer {token}".encode())],
            path="/nodes/config",
            store=store,
        )
        called, sent = await _run(scope)
        assert not called
        assert sent and sent[0]["status"] == 403

    @pytest.mark.asyncio
    async def test_remote_full_token_reaches_anything(self, tmp_path):
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Host", "host", scope="full")
        scope = _scope(
            "http",
            "100.64.0.5",
            headers=[(b"authorization", f"Bearer {token}".encode())],
            path="/nodes/config",
            store=store,
        )
        called, _ = await _run(scope)
        assert called

    @pytest.mark.asyncio
    async def test_remote_node_token_blocked_on_http(self, tmp_path):
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Phone", "ios", scope="node")
        scope = _scope(
            "http",
            "100.64.0.5",
            headers=[(b"authorization", f"Bearer {token}".encode())],
            path="/chat",
            store=store,
        )
        called, sent = await _run(scope)
        assert not called
        assert sent and sent[0]["status"] == 403

    @pytest.mark.asyncio
    async def test_paused_grant_denied(self, tmp_path):
        # A paused grant fails closed (401) even with a valid scope/route.
        store = DeviceTokenStore(path=tmp_path / "d.json")
        device_id, token = store.mint("Peer", "linux", scope="agent")
        store.set_status(device_id, "paused")
        scope = _scope(
            "http",
            "100.64.0.5",
            headers=[(b"authorization", f"Bearer {token}".encode())],
            path="/chat",
            store=store,
        )
        called, sent = await _run(scope)
        assert not called
        assert sent and sent[0]["status"] == 401
        # Resuming restores access.
        store.set_status(device_id, "active")
        called2, _ = await _run(scope)
        assert called2

    @pytest.mark.asyncio
    async def test_remote_ws_node_exempt(self):
        called, _ = await _run(_scope("websocket", "100.64.0.5", path="/ws/node"))
        assert called

    @pytest.mark.asyncio
    async def test_remote_ws_other_closed(self):
        called, sent = await _run(_scope("websocket", "100.64.0.5", path="/ws/other"))
        assert not called
        assert sent and sent[0]["type"] == "websocket.close"


def test_browser_node_page_is_public_but_not_the_devices_api():
    """The /node page must be exempt by EXACT path, never as a prefix.

    A joining device has no token, so the page itself must be fetchable. But
    exempting "/node" as a *prefix* would also match "/nodes/devices" and
    "/nodes/pending/{code}/approve", handing the entire device API to any
    unauthenticated remote caller.
    """
    assert is_http_exempt("/node")

    for guarded in (
        "/nodes",
        "/nodes/devices",
        "/nodes/pending",
        "/nodes/pending/ABC123/approve",
        "/nodes/grants",
        "/nodex",
    ):
        assert not is_http_exempt(guarded), f"{guarded} must stay behind auth"


# ── Web UI additions ────────────────────────────────────────────────────────


def test_query_token_only_for_stream_paths():
    from suzent.auth_boundary import extract_query_token

    assert extract_query_token("/events/stream", b"token=abc") == "abc"
    assert extract_query_token("/subagents/stream", b"x=1&token=abc") == "abc"
    # Everything else must keep using a header, so a token in the query is
    # ignored rather than honoured.
    assert extract_query_token("/config", b"token=abc") == ""
    assert extract_query_token("/chat", b"token=abc") == ""
    assert extract_query_token("/events/stream", b"") == ""


def test_host_header_allowed():
    from suzent.auth_boundary import host_header_allowed

    assert host_header_allowed("127.0.0.1:8000")
    assert host_header_allowed("localhost")
    assert host_header_allowed("[::1]:8000")
    assert host_header_allowed("")  # no name, nothing to rebind
    # A rebound DNS name pointing at loopback is the attack this catches.
    assert not host_header_allowed("attacker.example:8000")


def test_host_header_is_local_excludes_configured_names(monkeypatch):
    from suzent.auth_boundary import host_header_allowed, host_header_is_local

    monkeypatch.setenv("SUZENT_ALLOWED_HOSTS", "suzent.example.com")
    # Allowed (not a rebinding attempt) but not local (not trusted).
    assert host_header_allowed("suzent.example.com")
    assert not host_header_is_local("suzent.example.com")
    assert host_header_is_local("127.0.0.1:8000")


def test_host_header_extra_allowed(monkeypatch):
    from suzent.auth_boundary import host_header_allowed

    monkeypatch.setenv("SUZENT_ALLOWED_HOSTS", "suzent.example.com")
    assert host_header_allowed("suzent.example.com")
    assert not host_header_allowed("other.example.com")


class TestRebindingGuard:
    @pytest.mark.asyncio
    async def test_loopback_with_foreign_host_header_rejected(self):
        # DNS rebinding: the request really comes from 127.0.0.1, but the page
        # that made it thinks it is talking to attacker.example.
        scope = _scope("http", "127.0.0.1", headers=[(b"host", b"attacker.example")])
        called, sent = await _run(scope)
        assert not called
        assert sent[0]["status"] == 421

    @pytest.mark.asyncio
    async def test_loopback_with_loopback_host_header_passes(self):
        scope = _scope("http", "127.0.0.1", headers=[(b"host", b"127.0.0.1:8000")])
        called, _ = await _run(scope)
        assert called

    @pytest.mark.asyncio
    async def test_proxied_allowed_host_still_needs_a_token(self, monkeypatch):
        # A reverse proxy on this machine forwards an internet request: the ASGI
        # client is 127.0.0.1 and the Host is one the operator allowed. Allowing
        # the name defeats rebinding; it must not hand out unauthenticated
        # access to whoever was on the other side of the proxy.
        monkeypatch.setenv("SUZENT_ALLOWED_HOSTS", "suzent.example.com")
        scope = _scope("http", "127.0.0.1", headers=[(b"host", b"suzent.example.com")])
        called, sent = await _run(scope)
        assert not called
        assert sent[0]["status"] == 401

    @pytest.mark.asyncio
    async def test_proxied_allowed_host_accepts_a_valid_token(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SUZENT_ALLOWED_HOSTS", "suzent.example.com")
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Browser", "web", scope="full")
        scope = _scope(
            "http",
            "127.0.0.1",
            headers=[
                (b"host", b"suzent.example.com"),
                (b"authorization", f"Bearer {token}".encode()),
            ],
            store=store,
        )
        called, _ = await _run(scope)
        assert called

    @pytest.mark.asyncio
    async def test_stream_query_token_authenticates(self, tmp_path):
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Browser", "web", scope="full")
        scope = _scope(
            "http",
            "100.64.0.5",
            path="/events/stream",
            store=store,
        )
        scope["query_string"] = f"token={token}".encode()
        called, _ = await _run(scope)
        assert called

    @pytest.mark.asyncio
    async def test_query_token_rejected_on_other_paths(self, tmp_path):
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Browser", "web", scope="full")
        scope = _scope("http", "100.64.0.5", path="/config", store=store)
        scope["query_string"] = f"token={token}".encode()
        called, sent = await _run(scope)
        assert not called
        assert sent[0]["status"] == 401
