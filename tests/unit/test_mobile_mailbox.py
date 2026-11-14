"""Mailbox visibility and shared read state across paired devices and desktop."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.database import ChatDatabase, MailboxItemModel
from suzent.routes.mailbox_routes import _item_to_dict
from suzent.mobile.client_api import client_routes
from suzent.mobile.pairing import ClientPermissions, PairingStore


type MailboxClient = tuple[TestClient, PairingStore, ChatDatabase]


@pytest.fixture
def mailbox_client(
    temp_db: ChatDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MailboxClient]:
    store = PairingStore(tmp_path / "mobile.json")
    app = Starlette(routes=client_routes)
    app.state.mobile_store = store
    app.add_middleware(AuthBoundaryMiddleware)
    monkeypatch.setattr("suzent.mobile.client_api.get_database", lambda: temp_db)
    with TestClient(app, client=("192.0.2.1", 1234)) as client:
        yield client, store, temp_db


def headers(store: PairingStore, **permissions: object) -> dict[str, str]:
    invite = store.invite()
    pickup = store.claim(invite["pairing_id"], invite["invitation"], "Phone", "ios")
    store.decide(invite["pairing_id"], ClientPermissions(**permissions))
    result = store.collect(invite["pairing_id"], pickup["pickup_secret"])
    return {"Authorization": f"Bearer {result['token']}"}


def item(
    db: ChatDatabase, target: str | None = None, status: str = "notified"
) -> MailboxItemModel:
    return db.create_mailbox_item(
        signature="test",
        summary="Message",
        payload="Details",
        target_chat_id=target,
        route_status=status,
        headers_json='{"secret":"host-only"}',
        reason="host-only",
    )


def test_scope_applies_before_pagination_and_to_counts(
    mailbox_client: MailboxClient,
) -> None:
    client, store, db = mailbox_client
    shared = item(db, "shared")
    item(db, "private")
    item(db)
    item(db, "focal-suzent")
    auth = headers(store, chat_ids=["shared", "focal-suzent"])
    response = client.post(
        "/mobile/client/mailbox/page", headers=auth, json={"limit": 1}
    )
    assert response.status_code == 200
    page = response.json()
    assert [row["id"] for row in page["items"]] == [shared.id]
    assert page["unread"] == 1
    assert page["hasMore"] is False
    assert "headers" not in page["items"][0]
    assert "reason" not in page["items"][0]
    assert page["items"][0]["payload"] == "Details"
    assert page["items"][0]["presentation"] == _item_to_dict(shared)["presentation"]
    assert "host-only" not in str(page["items"][0]["presentation"])


def test_full_grant_lists_global_events_and_categories(
    mailbox_client: MailboxClient,
) -> None:
    client, store, db = mailbox_client
    notice = item(db)
    event = item(db, status="unrouted")
    auth = headers(store, all_chats=True)
    page = client.post("/mobile/client/mailbox/page", headers=auth, json={}).json()
    assert [row["id"] for row in page["items"]] == [notice.id]
    page = client.post(
        "/mobile/client/mailbox/page",
        headers=auth,
        json={"category": "all", "limit": 1},
    ).json()
    assert [row["id"] for row in page["items"]] == [event.id]
    assert page["hasMore"] is True
    page = client.post(
        "/mobile/client/mailbox/page",
        headers=auth,
        json={"category": "all", "limit": 1, "offset": 1},
    ).json()
    assert [row["id"] for row in page["items"]] == [notice.id]
    assert page["hasMore"] is False


def test_read_all_never_marks_unshared_or_global_events(
    mailbox_client: MailboxClient,
) -> None:
    client, store, db = mailbox_client
    shared = item(db, "shared")
    private = item(db, "private")
    global_item = item(db)
    event = item(db, "shared", "routed")
    auth = headers(store, chat_ids=["shared"])
    response = client.post(
        "/mobile/client/mailbox/read", headers=auth, json={"all": True}
    )
    assert response.json() == {"marked": 1, "unread": 0}
    assert db.get_mailbox_item(shared.id).read_at is not None
    assert all(
        db.get_mailbox_item(row.id).read_at is None
        for row in (private, global_item, event)
    )
    assert db.count_unread_mailbox_notifications() == 2
    assert (
        client.post(
            "/mobile/client/mailbox/read", headers=auth, json={"all": True}
        ).json()["marked"]
        == 0
    )


def test_explicit_read_ids_and_two_device_sync(mailbox_client: MailboxClient) -> None:
    client, store, db = mailbox_client
    shared = item(db, "shared")
    private = item(db, "private")
    auth = headers(store, chat_ids=["shared"])
    second = headers(store, all_chats=True)
    result = client.post(
        "/mobile/client/mailbox/read",
        headers=auth,
        json={"ids": [shared.id, private.id]},
    ).json()
    assert result == {"marked": 1, "unread": 0}
    page = client.post("/mobile/client/mailbox/page", headers=second, json={}).json()
    assert page["unread"] == 1
    assert (
        next(row for row in page["items"] if row["id"] == shared.id)["readAt"]
        is not None
    )
    # Desktop uses the same database operation and read_at, not a delivery queue.
    db.mark_mailbox_notifications_read([private.id])
    assert (
        client.post("/mobile/client/mailbox/page", headers=second, json={}).json()[
            "unread"
        ]
        == 0
    )


def test_empty_grant_is_not_global_access(mailbox_client: MailboxClient) -> None:
    client, store, db = mailbox_client
    item(db)
    auth = headers(store)
    assert client.post("/mobile/client/mailbox/page", headers=auth, json={}).json() == {
        "items": [],
        "unread": 0,
        "hasMore": False,
    }
    assert (
        client.post(
            "/mobile/client/mailbox/read", headers=auth, json={"all": True}
        ).json()["marked"]
        == 0
    )
    assert db.count_unread_mailbox_notifications() == 1


def test_revocation_and_scope_changes_take_effect(
    mailbox_client: MailboxClient,
) -> None:
    client, store, db = mailbox_client
    item(db)
    auth = headers(store, all_chats=True)
    device = client.get("/mobile/client/session", headers=auth).json()["device"][
        "device_id"
    ]
    assert client.get("/mobile/client/session", headers=auth).json()["mailbox"] == 1
    store.set_permissions(device, ClientPermissions())
    assert (
        client.post("/mobile/client/mailbox/page", headers=auth, json={}).json()[
            "unread"
        ]
        == 0
    )
    store.revoke(device)
    for route, body in [("page", {}), ("read", {"all": True})]:
        assert (
            client.post(
                f"/mobile/client/mailbox/{route}", headers=auth, json=body
            ).status_code
            == 401
        )
        assert (
            client.post(f"/mobile/client/mailbox/{route}", json=body).status_code == 401
        )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"ids": []},
        {"ids": [True]},
        {"ids": [-1]},
        {"ids": [1], "all": True},
        {"ids": "1"},
        {"all": "yes"},
    ],
)
def test_read_requires_explicit_valid_selection(
    mailbox_client: MailboxClient, body: dict[str, object]
) -> None:
    client, store, db = mailbox_client
    item(db)
    assert (
        client.post(
            "/mobile/client/mailbox/read",
            headers=headers(store, all_chats=True),
            json=body,
        ).status_code
        == 400
    )
    assert db.count_unread_mailbox_notifications() == 1


@pytest.mark.parametrize(
    "body",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"category": "private"},
        {"offset": True},
    ],
)
def test_page_validation(
    mailbox_client: MailboxClient, body: dict[str, object]
) -> None:
    client, store, _ = mailbox_client
    assert (
        client.post(
            "/mobile/client/mailbox/page", headers=headers(store), json=body
        ).status_code
        == 400
    )
