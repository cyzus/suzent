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
        assert rec["mode"] == "one_way"

        listed = store.list_peers()
        assert len(listed) == 1
        assert "token" not in listed[0]  # token never exposed in listings

        assert store.set_mode(pid, "mutual") is True
        assert store.get(pid)["mode"] == "mutual"

        assert store.remove(pid) is True
        assert store.get(pid) is None
        assert store.remove(pid) is False

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
