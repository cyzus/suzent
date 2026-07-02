"""
Control-grant: grant-request lifecycle, one-time token pickup, anti-spam cap,
and the controller-side peer store.
"""

import pytest

from suzent.nodes.device_store import DeviceTokenStore
from suzent.nodes.manager import MAX_PENDING_GRANTS, NodeManager
from suzent.nodes.peer_store import PeerGrantStore


def _mgr(tmp_path):
    return NodeManager(device_store=DeviceTokenStore(path=tmp_path / "d.json"))


class TestGrantRequests:
    def test_request_approve_pickup_once(self, tmp_path):
        mgr = _mgr(tmp_path)
        rid = mgr.add_grant_request("A", "100.0.0.1")
        assert len(mgr.list_grant_requests()) == 1

        # No token before approval.
        assert mgr.take_grant_result(rid) == {"status": "pending"}

        assert mgr.approve_grant(rid) is True
        first = mgr.take_grant_result(rid)
        assert first["status"] == "approved" and first["token"]
        token = first["token"]

        # Token is served exactly once; the minted token still authorizes.
        second = mgr.take_grant_result(rid)
        assert second == {"status": "approved"}
        assert mgr.device_store.verify(token) is not None
        # Approved requests no longer show in the operator's pending list.
        assert mgr.list_grant_requests() == []

    def test_list_exposes_controller_addr(self, tmp_path):
        # The requester's address is surfaced so the UI can match a pending
        # request to an existing peer row (inline approve, no duplicate card).
        mgr = _mgr(tmp_path)
        addr = "http://peer.example:25314"
        mgr.add_grant_request("peer-host.local", "10.0.0.5", controller_addr=addr)
        listed = mgr.list_grant_requests()[0]
        assert listed["controller_addr"] == addr

    def test_reapprove_supersedes_prior_grant(self, tmp_path):
        # Re-requesting from the same machine replaces its grant instead of
        # accumulating a new token each time (matched by controller_addr).
        mgr = _mgr(tmp_path)
        addr = "http://peer.example:25314"
        r1 = mgr.add_grant_request("peer.local", "10.0.0.5", controller_addr=addr)
        assert mgr.approve_grant(r1) is True
        r2 = mgr.add_grant_request("peer.local", "10.0.0.5", controller_addr=addr)
        assert mgr.approve_grant(r2) is True
        # Only one live grant for that address.
        grants = [
            d for d in mgr.device_store.list_devices() if d["callback_url"] == addr
        ]
        assert len(grants) == 1

    def test_supersede_by_identity_across_addresses(self, tmp_path):
        # Same node_identity from two DIFFERENT addresses (LAN vs Tailscale) still
        # collapses to one grant — identity wins over address.
        mgr = _mgr(tmp_path)
        nid = "abc123identity"
        r1 = mgr.add_grant_request(
            "peer.local",
            "10.0.0.5",
            controller_addr="http://10.0.0.5:25314",
            controller_identity=nid,
        )
        assert mgr.approve_grant(r1) is True
        r2 = mgr.add_grant_request(
            "peer.local",
            "100.64.0.9",
            controller_addr="http://100.64.0.9:25314",
            controller_identity=nid,
        )
        assert mgr.approve_grant(r2) is True
        grants = [
            d for d in mgr.device_store.list_devices() if d["node_identity"] == nid
        ]
        assert len(grants) == 1

    def test_deny(self, tmp_path):
        mgr = _mgr(tmp_path)
        rid = mgr.add_grant_request("A", "")
        assert mgr.deny_grant(rid) is True
        assert mgr.take_grant_result(rid) == {"status": "denied"}
        assert mgr.approve_grant(rid) is False  # can't approve after deny

    def test_unknown_request(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.take_grant_result("nope") is None
        assert mgr.approve_grant("nope") is False
        assert mgr.deny_grant("nope") is False

    def test_spam_cap(self, tmp_path):
        mgr = _mgr(tmp_path)
        for _ in range(MAX_PENDING_GRANTS):
            mgr.add_grant_request("x", "")
        with pytest.raises(ValueError):
            mgr.add_grant_request("overflow", "")


class TestPeerStore:
    def test_add_get_mode_remove(self, tmp_path):
        store = PeerGrantStore(path=tmp_path / "peers.json")
        pid = store.add("Mac", "http://100.0.0.2:25314", "tok123")
        rec = store.get(pid)
        assert rec["token"] == "tok123"
        assert rec["mode"] == "trigger"

        listed = store.list_peers()
        assert len(listed) == 1
        assert "token" not in listed[0]  # token never exposed in listings

        assert store.set_mode(pid, "paused") is True
        assert store.get(pid)["mode"] == "paused"

        assert store.remove(pid) is True
        assert store.get(pid) is None
        assert store.remove(pid) is False

    def test_legacy_modes_migrated(self, tmp_path):
        import json

        path = tmp_path / "peers.json"
        path.write_text(
            json.dumps(
                {
                    "peers": {
                        "a": {
                            "name": "A",
                            "base_url": "http://h:1",
                            "token": "t",
                            "mode": "one_way",
                        },
                        "b": {
                            "name": "B",
                            "base_url": "http://h:2",
                            "token": "t",
                            "mode": "mutual",
                            "reverse_device_id": "rev1",
                        },
                    }
                }
            )
        )
        store = PeerGrantStore(path=path)
        assert store.get("a")["mode"] == "trigger"
        assert store.get("b")["mode"] == "trigger"
        # mutual's inbound half survives as the reverse grant.
        assert store.get("b")["reverse_device_id"] == "rev1"
        listed = {p["peer_id"]: p for p in store.list_peers()}
        assert listed["b"]["reverse_enabled"] is True
        assert listed["a"]["reverse_enabled"] is False

    def test_add_dedupes_by_base_url(self, tmp_path):
        store = PeerGrantStore(path=tmp_path / "peers.json")
        a = store.add("Mac", "http://h:1/", "t1")
        b = store.add("Mac2", "http://h:1", "t2")  # same base_url (trailing slash)
        assert a == b
        assert store.get(a)["token"] == "t2"
        assert len(store.list_peers()) == 1

    def test_persistence(self, tmp_path):
        path = tmp_path / "peers.json"
        s1 = PeerGrantStore(path=path)
        pid = s1.add("Mac", "http://h:1", "t")
        s2 = PeerGrantStore(path=path)
        assert s2.get(pid) is not None


# ─── Revocation propagation (Phase 2b) ───────────────────────────────


def test_node_identity_stable_and_persisted(tmp_path, monkeypatch):
    import suzent.nodes.node_identity as ni

    monkeypatch.setattr(ni, "_PATH", tmp_path / "node_identity.json")
    monkeypatch.setattr(ni, "_cached", None)
    first = ni.get_node_identity()
    assert first  # generated
    # Same process (cached) and a fresh read both return the same id.
    assert ni.get_node_identity() == first
    monkeypatch.setattr(ni, "_cached", None)
    assert ni.get_node_identity() == first  # persisted across "restart"


def test_device_store_callback(tmp_path):
    store = DeviceTokenStore(path=tmp_path / "d.json")
    did, _tok = store.mint("Peer", "peer", scope="agent", callback_url="http://b:1")
    rec = store.get_by_device_id(did)
    assert rec is not None and rec["callback_url"] == "http://b:1"
    assert store.get_by_device_id("nope") is None


def test_grant_changed_drops_revoked_peer(tmp_path, monkeypatch):
    import httpx
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from suzent.nodes.peer_store import PeerGrantStore
    from suzent.routes.suzent_channel_routes import suzent_channel_grant_changed

    store = PeerGrantStore(path=tmp_path / "peers.json")
    pid = store.add("B", "http://b:1", "tok")

    class FakeResp:
        status_code = 403  # peer says our token is no longer valid

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    app = Starlette(
        routes=[
            Route(
                "/channels/suzent/grant-changed",
                suzent_channel_grant_changed,
                methods=["POST"],
            )
        ]
    )
    app.state.peer_store = store
    client = TestClient(app)

    r = client.post("/channels/suzent/grant-changed", json={})
    assert r.status_code == 200
    assert r.json()["removed"] == 1
    assert store.get(pid) is None  # revoked peer dropped after self-verify


def test_list_peers_outbound_status(tmp_path, monkeypatch):
    """Outbound status = ready | revoked | offline based on reachability + token."""
    import httpx
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from suzent.nodes import discovery
    from suzent.nodes.peer_store import PeerGrantStore
    from suzent.routes.node_routes import list_peers

    store = PeerGrantStore(path=tmp_path / "peers.json")
    ready = store.add("Ready", "http://ready:25314", "goodtok")
    revoked = store.add("Revoked", "http://revoked:25314", "badtok")
    offline = store.add("Offline", "http://offline:25314", "tok")

    async def fake_reachable(host, port, timeout=1.5):
        return host != "offline"

    monkeypatch.setattr(discovery, "probe_reachable", fake_reachable)

    class FakeResp:
        def __init__(self, code, body):
            self.status_code = code
            self._body = body

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def get(self, url, headers=None, **k):
            tok = (headers or {}).get("Authorization", "")
            if "goodtok" in tok:
                return FakeResp(200, {"ok": True, "peer_id": "p123"})
            return FakeResp(401, {"error": "unauthorized"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    app = Starlette(routes=[Route("/nodes/peers", list_peers, methods=["GET"])])
    app.state.peer_store = store
    client = TestClient(app)

    peers = {p["peer_id"]: p for p in client.get("/nodes/peers").json()["peers"]}
    assert peers[ready]["outbound_status"] == "ready"
    assert peers[revoked]["outbound_status"] == "revoked"
    assert peers[offline]["outbound_status"] == "offline"


def test_list_peers_status_is_cached(tmp_path, monkeypatch):
    """A second poll within the TTL serves cached status without re-probing."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from suzent.nodes import discovery
    from suzent.nodes.peer_store import PeerGrantStore
    from suzent.routes import node_routes

    node_routes._peer_status_cache.clear()
    store = PeerGrantStore(path=tmp_path / "peers.json")
    store.add("Cached", "http://cached:25314", "tok")

    probes = {"n": 0}

    async def counting_reachable(host, port, timeout=1.5):
        probes["n"] += 1
        return False  # offline → no whoami; status computed from probe alone

    monkeypatch.setattr(discovery, "probe_reachable", counting_reachable)

    app = Starlette(
        routes=[Route("/nodes/peers", node_routes.list_peers, methods=["GET"])]
    )
    app.state.peer_store = store
    client = TestClient(app)

    client.get("/nodes/peers")  # cold → probes
    client.get("/nodes/peers")  # warm → served from cache
    assert probes["n"] == 1  # probed once, not twice

    # ?refresh=1 forces a re-probe.
    client.get("/nodes/peers?refresh=1")
    assert probes["n"] == 2


def test_remove_peer_also_revokes_reverse_grant(tmp_path):
    """Removing a peer fully unlinks: drops our token AND revokes the reverse
    grant so the peer can no longer drive us either."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from suzent.nodes.device_store import DeviceTokenStore
    from suzent.nodes.manager import NodeManager
    from suzent.nodes.peer_store import PeerGrantStore
    from suzent.routes.node_routes import remove_peer

    ds = DeviceTokenStore(path=tmp_path / "d.json")
    mgr = NodeManager(device_store=ds)
    ps = PeerGrantStore(path=tmp_path / "peers.json")

    # A peer we drive at a given address, plus TWO inbound grants for the same
    # machine: a reverse grant (tracked in reverse_device_id) AND an independent
    # grant approved via a control request (callback_url = the peer's address,
    # NOT in reverse_device_id). Remove must kill both.
    addr = "http://peer.example:25314"
    pid = ps.add("Peer", addr, "theirtok")
    rev_id, _t1 = ds.mint("Peer", "peer", scope="agent")
    ps.set_reverse_device_id(pid, rev_id)
    approve_id, _t2 = ds.mint("Peer", "peer", scope="agent", callback_url=addr)
    assert ds.get_by_device_id(rev_id) is not None
    assert ds.get_by_device_id(approve_id) is not None

    app = Starlette(
        routes=[Route("/nodes/peers/{peer_id}/remove", remove_peer, methods=["POST"])]
    )
    app.state.peer_store = ps
    app.state.node_manager = mgr
    client = TestClient(app)

    r = client.post(f"/nodes/peers/{pid}/remove")
    assert r.status_code == 200 and r.json()["success"] is True
    assert ps.get(pid) is None  # outbound gone
    assert ds.get_by_device_id(rev_id) is None  # reverse grant revoked
    # The separately-approved inbound grant (matched by address) is also revoked,
    # so the peer can no longer trigger us after Remove.
    assert ds.get_by_device_id(approve_id) is None
