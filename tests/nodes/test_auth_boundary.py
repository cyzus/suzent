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
    token_authorized,
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


def test_token_authorized(tmp_path):
    store = DeviceTokenStore(path=tmp_path / "d.json")
    _id, token = store.mint("Phone", "ios")

    # Valid durable device token.
    assert token_authorized(token, store, "approve", "")
    # Shared secret in token mode.
    assert token_authorized("s3cret", store, "token", "s3cret")
    # Wrong / empty.
    assert not token_authorized("nope", store, "approve", "")
    assert not token_authorized("", store, "token", "s3cret")
    # Shared secret ignored when mode isn't 'token'.
    assert not token_authorized("s3cret", store, "open", "s3cret")


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
    async def test_remote_with_valid_token_passes(self, tmp_path):
        store = DeviceTokenStore(path=tmp_path / "d.json")
        _id, token = store.mint("Peer", "linux")
        scope = _scope(
            "http",
            "100.64.0.5",
            headers=[(b"authorization", f"Bearer {token}".encode())],
            store=store,
        )
        called, _ = await _run(scope)
        assert called

    @pytest.mark.asyncio
    async def test_remote_ws_node_exempt(self):
        called, _ = await _run(_scope("websocket", "100.64.0.5", path="/ws/node"))
        assert called

    @pytest.mark.asyncio
    async def test_remote_ws_other_closed(self):
        called, sent = await _run(_scope("websocket", "100.64.0.5", path="/ws/other"))
        assert not called
        assert sent and sent[0]["type"] == "websocket.close"
