"""
Tests for the network auth boundary: loopback is trusted, remote callers need a
valid node token, and the /ws/node handshake is exempt.
"""

from types import SimpleNamespace

import pytest

from suzent.auth_boundary import (
    AuthBoundaryMiddleware,
    extract_token,
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
    assert not scope_allows("agent", "/nodes/config")
    assert not scope_allows("agent", "/nodes/peers")
    assert not scope_allows("agent", "/sandbox/files")
    assert not scope_allows("node", "/chat")
    assert not scope_allows(None, "/chat")


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
    async def test_loopback_passes(self, monkeypatch):
        monkeypatch.setattr(
            "suzent.config.CONFIG.node_auth_mode", "open", raising=False
        )
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
    async def test_remote_ws_node_exempt(self):
        called, _ = await _run(_scope("websocket", "100.64.0.5", path="/ws/node"))
        assert called

    @pytest.mark.asyncio
    async def test_remote_ws_other_closed(self):
        called, sent = await _run(_scope("websocket", "100.64.0.5", path="/ws/other"))
        assert not called
        assert sent and sent[0]["type"] == "websocket.close"
