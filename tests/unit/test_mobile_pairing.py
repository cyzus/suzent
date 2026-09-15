import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from suzent.mobile.pairing import ClientPermissions, PairingError, PairingStore


def claimed(store):
    invitation = store.invite()
    pickup = store.claim(
        invitation["pairing_id"], invitation["invitation"], "Phone", "ios"
    )
    return invitation, pickup


def test_approval_pickup_persistence_and_revocation(tmp_path):
    path = tmp_path / "clients.json"
    store = PairingStore(path)
    invitation, pickup = claimed(store)
    args = invitation["pairing_id"], pickup["pickup_secret"]
    assert store.collect(*args) == {"status": "pending"}
    assert "pickup_secret" not in json.dumps(store.pending())
    store.decide(args[0], ClientPermissions(chat_ids=["one"], send=True))
    result = store.collect(*args)
    token = result["token"]
    assert token not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    restored = PairingStore(path)
    grant = restored.verify(token)
    assert grant.permissions.permits_chat("one")
    assert not grant.permissions.permits_chat("two")
    assert not grant.permissions.stop
    with pytest.raises(PairingError):
        store.collect(*args)
    assert restored.revoke(grant.device_id)
    assert restored.verify(token) is None
    assert PairingStore(path).verify(token) is None


def test_single_claim_under_concurrency(tmp_path):
    store = PairingStore(tmp_path / "clients.json")
    invitation = store.invite()

    def claim(_):
        try:
            return store.claim(
                invitation["pairing_id"], invitation["invitation"], "Phone", "android"
            )
        except PairingError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(result is not None for result in pool.map(claim, range(16))) == 1


def test_expiry_denial_and_wrong_secrets(tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "clients.json")
    invitation, pickup = claimed(store)
    with pytest.raises(PairingError):
        store.collect(invitation["pairing_id"], "wrong")
    store.decide(invitation["pairing_id"], None)
    assert store.collect(invitation["pairing_id"], pickup["pickup_secret"]) == {
        "status": "denied"
    }
    monkeypatch.setattr(
        "suzent.mobile.pairing.time.time", lambda: invitation["expires_at"] + 1
    )
    with pytest.raises(PairingError):
        store.collect(invitation["pairing_id"], pickup["pickup_secret"])
    assert store.pending() == []


def test_failed_persist_never_issues_grant(tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "clients.json")
    invitation, pickup = claimed(store)
    store.decide(invitation["pairing_id"], ClientPermissions())

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("suzent.mobile.pairing.os.replace", fail)
    with pytest.raises(OSError):
        store.collect(invitation["pairing_id"], pickup["pickup_secret"])
    assert store.devices() == []


def test_remote_operator_routes_remain_protected(tmp_path):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    from suzent.auth_boundary import AuthBoundaryMiddleware
    from suzent.routes.mobile_routes import mobile_routes

    app = Starlette(routes=mobile_routes)
    app.state.mobile_store = PairingStore(tmp_path / "clients.json")
    app.add_middleware(AuthBoundaryMiddleware)
    with TestClient(app, client=("192.0.2.1", 3000)) as client:
        assert client.get("/mobile/capabilities").status_code == 200
        assert client.post("/mobile/pairing/invite").status_code == 401
        assert client.get("/mobile/pairing/pending").status_code == 401
        assert client.get("/mobile/devices").status_code == 401
        assert client.post("/mobile/pairing/abc/decide", json={}).status_code == 401
        assert client.post("/mobile/pairing/claim", json={}).status_code == 400
        assert client.post("/mobile/pairing/collect", json={}).status_code == 400
        assert client.get("/mobile/pairing/claim/extra").status_code == 401


def test_new_conversations_remain_valid_after_store_reload(tmp_path):
    path = tmp_path / "clients.json"
    store = PairingStore(path)
    invitation, pickup = claimed(store)
    store.decide(
        invitation["pairing_id"],
        ClientPermissions(
            chat_ids=[str(index) for index in range(1000)], create_chats=True
        ),
    )
    result = store.collect(invitation["pairing_id"], pickup["pickup_secret"])
    assert store.add_chat(result["device"]["device_id"], "new")
    assert PairingStore(path).verify(result["token"]).permissions.permits_chat("new")


def test_phone_confirmation_uses_frozen_desktop_scope(tmp_path):
    store = PairingStore(tmp_path / "clients.json")
    permissions = ClientPermissions(chat_ids=["shared"], send=True)
    invite = store.invite(permissions, "Test desktop")
    permissions.chat_ids.append("private")
    preview = store.preview(invite["pairing_id"])
    assert invite["approval"] == "phone"
    assert preview["desktop_name"] == "Test desktop"
    assert preview["permissions"]["chat_ids"] == ["shared"]
    assert store.devices() == []
    assert "invitation" not in preview
    pickup = store.claim(
        invite["pairing_id"],
        invite["invitation"],
        "Phone",
        "android",
        confirm_permissions=True,
    )
    assert store.devices() == []
    assert store.pending() == []
    with pytest.raises(PairingError):
        store.decide(invite["pairing_id"], ClientPermissions(all_chats=True))
    result = store.collect(invite["pairing_id"], pickup["pickup_secret"])
    assert result["status"] == "approved"
    assert (
        result["device"]["permissions"]
        == ClientPermissions(chat_ids=["shared"], send=True).model_dump()
    )
    with pytest.raises(PairingError):
        store.collect(invite["pairing_id"], pickup["pickup_secret"])
    with pytest.raises(PairingError):
        store.claim(invite["pairing_id"], invite["invitation"], "Other", "ios")
    assert store.revoke(result["device"]["device_id"])
    assert store.verify(result["token"]) is None


@pytest.mark.parametrize("claimed_first", [False, True])
def test_cancel_preapproved_invitation_before_credential_delivery(
    tmp_path, claimed_first
):
    store = PairingStore(tmp_path / "clients.json")
    invite = store.invite(ClientPermissions(create_chats=True))
    pickup = None
    if claimed_first:
        pickup = store.claim(
            invite["pairing_id"],
            invite["invitation"],
            "Phone",
            "ios",
            confirm_permissions=True,
        )
    assert store.cancel(invite["pairing_id"])
    assert not store.cancel(invite["pairing_id"])
    with pytest.raises(PairingError):
        store.preview(invite["pairing_id"])
    with pytest.raises(PairingError):
        if pickup:
            store.collect(invite["pairing_id"], pickup["pickup_secret"])
        else:
            store.claim(invite["pairing_id"], invite["invitation"], "Phone", "ios")
    assert store.devices() == []


def test_preapproved_invitation_expires_without_creating_a_grant(tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "clients.json")
    invite = store.invite(ClientPermissions(send=True))
    monkeypatch.setattr(
        "suzent.mobile.pairing.time.time", lambda: invite["expires_at"] + 1
    )
    with pytest.raises(PairingError):
        store.preview(invite["pairing_id"])
    with pytest.raises(PairingError):
        store.claim(invite["pairing_id"], invite["invitation"], "Phone", "ios")
    assert store.devices() == []


def test_concurrent_phone_confirmation_issues_only_one_grant(tmp_path):
    store = PairingStore(tmp_path / "clients.json")
    invite = store.invite(ClientPermissions(create_chats=True))

    def accept(_):
        try:
            pickup = store.claim(
                invite["pairing_id"],
                invite["invitation"],
                "Phone",
                "android",
                confirm_permissions=True,
            )
            return store.collect(invite["pairing_id"], pickup["pickup_secret"])
        except PairingError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(value is not None for value in pool.map(accept, range(16))) == 1
    assert len(store.devices()) == 1
