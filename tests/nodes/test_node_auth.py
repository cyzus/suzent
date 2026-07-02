"""
Tests for node auth (operator-gated approval), durable device tokens, and
per-invoke timeout.
"""

import asyncio

import pytest

from suzent.nodes.base import NodeCapability
from suzent.nodes.device_store import DeviceTokenStore
from suzent.nodes.manager import NodeManager
from suzent.nodes.models import ConnectMessage


def make_store(tmp_path):
    return DeviceTokenStore(path=tmp_path / "devices.json")


class FakeWS:
    """Minimal stand-in for a Starlette WebSocket."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self.close_code = None

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000, reason=""):
        self.closed = True
        self.close_code = code


# ─── Durable device-token store ──────────────────────────────────────


class TestDeviceTokenStore:
    def test_mint_and_verify(self, tmp_path):
        store = make_store(tmp_path)
        device_id, token = store.mint("Phone", "ios")
        rec = store.verify(token)
        assert rec is not None
        assert rec["device_id"] == device_id
        assert rec["display_name"] == "Phone"
        assert store.verify("bad-token") is None
        assert store.verify("") is None

    def test_token_hint_is_head_tail_not_secret(self, tmp_path):
        store = make_store(tmp_path)
        _id, token = store.mint("Host", "host", scope="full")
        listed = store.list_devices()[0]
        hint = listed["token_hint"]
        # A non-secret fingerprint: head…tail, and never the full token.
        assert hint == f"{token[:6]}…{token[-4:]}"
        assert token not in hint
        assert len(hint) < len(token)

    def test_persistence_across_reload(self, tmp_path):
        path = tmp_path / "devices.json"
        store = DeviceTokenStore(path=path)
        _id, token = store.mint("PC", "linux")
        reloaded = DeviceTokenStore(path=path)
        assert reloaded.verify(token) is not None

    def test_list_hides_token_and_revoke(self, tmp_path):
        store = make_store(tmp_path)
        device_id, token = store.mint("Phone", "ios")
        listed = store.list_devices()
        assert len(listed) == 1
        assert listed[0]["device_id"] == device_id
        assert listed[0]["status"] == "active"  # minted active by default
        assert "token" not in listed[0]  # raw token never exposed
        assert store.revoke(device_id) is True
        assert store.verify(token) is None
        assert store.revoke("nonexistent") is False

    def test_set_status_pause_resume(self, tmp_path):
        store = make_store(tmp_path)
        device_id, token = store.mint("Phone", "ios", scope="agent")
        assert store.set_status(device_id, "paused") is True
        # verify() still returns the raw record (used for callback lookup)…
        assert store.verify(token)["status"] == "paused"
        assert store.set_status(device_id, "active") is True
        assert store.verify(token)["status"] == "active"
        assert store.set_status(device_id, "bogus") is False  # invalid status
        assert store.set_status("nonexistent", "paused") is False


# ─── Manager pairing / approval ──────────────────────────────────────


class TestPairing:
    @pytest.mark.asyncio
    async def test_approve_mints_durable_token(self, tmp_path):
        mgr = NodeManager(device_store=make_store(tmp_path))
        fut = asyncio.get_running_loop().create_future()
        code = mgr.add_pending(
            "Phone", "ios", [NodeCapability(name="camera.snap")], fut
        )
        assert len(mgr.list_pending()) == 1

        ok, token = mgr.approve_pending(code)
        assert ok and token
        assert fut.result() == token
        assert mgr.device_store.verify(token) is not None
        assert mgr.list_pending() == []  # consumed

    @pytest.mark.asyncio
    async def test_deny_resolves_false_and_consumes(self, tmp_path):
        mgr = NodeManager(device_store=make_store(tmp_path))
        fut = asyncio.get_running_loop().create_future()
        code = mgr.add_pending("Phone", "ios", [], fut)
        assert mgr.deny_pending(code) is True
        assert fut.result() is False
        assert mgr.deny_pending(code) is False  # already gone

    def test_approve_unknown_code(self, tmp_path):
        mgr = NodeManager(device_store=make_store(tmp_path))
        ok, token = mgr.approve_pending("ZZZZZZ")
        assert ok is False and token == ""

    def test_list_devices_connected_flag(self, tmp_path):
        mgr = NodeManager(device_store=make_store(tmp_path))
        mgr.device_store.mint("Phone", "ios")
        devs = mgr.list_devices()
        assert len(devs) == 1
        assert devs[0]["connected"] is False


# ─── Handshake authorization ─────────────────────────────────────────

from suzent.routes.node_routes import _authorize_node  # noqa: E402


class TestAuthorize:
    @pytest.mark.asyncio
    async def test_device_token_fast_path(self, tmp_path):
        # A known device token connects silently, skipping approval.
        store = make_store(tmp_path)
        _id, token = store.mint("Phone", "ios")
        mgr = NodeManager(device_store=store)
        ok, t = await _authorize_node(
            FakeWS(),
            mgr,
            ConnectMessage(display_name="Phone", device_token=token),
            [],
        )
        assert ok and t == ""  # no new token minted

    @pytest.mark.asyncio
    async def test_approve_flow_grants_token(self, tmp_path):
        mgr = NodeManager(device_store=make_store(tmp_path))
        ws = FakeWS()
        msg = ConnectMessage(display_name="Phone", platform="ios")
        task = asyncio.create_task(_authorize_node(ws, mgr, msg, []))

        # Wait for the pending entry + the "pending" response.
        for _ in range(100):
            if mgr.list_pending():
                break
            await asyncio.sleep(0.01)
        pend = mgr.list_pending()
        assert len(pend) == 1
        assert any(m.get("type") == "pending" for m in ws.sent)

        ok_app, minted = mgr.approve_pending(pend[0]["pairing_code"])
        assert ok_app
        ok, token = await task
        assert ok and token == minted

    @pytest.mark.asyncio
    async def test_approve_flow_denied(self, tmp_path):
        mgr = NodeManager(device_store=make_store(tmp_path))
        ws = FakeWS()
        task = asyncio.create_task(
            _authorize_node(ws, mgr, ConnectMessage(display_name="Phone"), [])
        )
        for _ in range(100):
            if mgr.list_pending():
                break
            await asyncio.sleep(0.01)
        mgr.deny_pending(mgr.list_pending()[0]["pairing_code"])
        ok, _ = await task
        assert ok is False
        assert ws.closed


# ─── Per-invoke timeout ──────────────────────────────────────────────


class TestInvokeTimeout:
    @pytest.mark.asyncio
    async def test_ws_node_respects_timeout_override(self):
        from suzent.nodes.ws_node import WebSocketNode

        class WS:
            async def send_json(self, data):
                pass

        node = WebSocketNode(WS(), "id", "Phone", "ios", [NodeCapability(name="x")])
        # No result is ever delivered, so a short override must time out fast.
        with pytest.raises(TimeoutError):
            await node.invoke("x", {}, timeout=0.05)


class TestNodeHostSecrets:
    @pytest.mark.asyncio
    async def test_run_injects_stored_secrets(self, monkeypatch):
        """The node host is a separate process; it must load stored API keys into
        os.environ on startup so capabilities (e.g. speaker.speak TTS) find them."""
        from suzent.nodes import node_host

        injected = {"called": False}

        class FakeSM:
            def inject_all_to_env(self):
                injected["called"] = True
                return 3

        monkeypatch.setattr("suzent.core.secrets.get_secret_manager", lambda: FakeSM())

        host = node_host.NodeHost(gateway_url="ws://x:1/ws/node")
        host._stop = True  # skip the reconnect loop; we only assert startup work
        await host.run()

        assert injected["called"] is True
