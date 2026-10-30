from __future__ import annotations

from datetime import datetime, timezone

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.mobile.client_api import client_routes
from suzent.mobile.pairing import ClientPermissions, PairingStore


@pytest.fixture
def pagination_client(temp_db, tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "pagination-devices.json")
    app = Starlette(routes=client_routes)
    app.state.mobile_store = store
    app.add_middleware(AuthBoundaryMiddleware)
    monkeypatch.setattr("suzent.mobile.client_api.get_database", lambda: temp_db)

    def headers(**permissions: object) -> dict[str, str]:
        invite = store.invite()
        pickup = store.claim(invite["pairing_id"], invite["invitation"], "Phone", "ios")
        store.decide(invite["pairing_id"], ClientPermissions(**permissions))
        result = store.collect(invite["pairing_id"], pickup["pickup_secret"])
        return {"Authorization": f"Bearer {result['token']}"}

    with TestClient(app, client=("192.0.2.1", 1234)) as client:
        yield client, headers


def test_page_boundaries_and_search_beyond_first_page(pagination_client, temp_db):
    client, headers = pagination_client
    target = temp_db.create_chat("An older needle", {})
    for index in range(34):
        temp_db.create_chat(f"Recent {index}", {})
    auth = headers(all_chats=True)
    first = client.post("/mobile/client/chat-page", headers=auth, json={}).json()
    assert len(first["chats"]) == 30
    assert first["total"] == 35
    assert first["nextOffset"] == 30
    second = client.post(
        "/mobile/client/chat-page", headers=auth, json={"offset": 30}
    ).json()
    assert len(second["chats"]) == 5
    assert second["nextOffset"] is None
    assert {c["id"] for c in first["chats"]}.isdisjoint(
        c["id"] for c in second["chats"]
    )
    found = client.post(
        "/mobile/client/chat-page",
        headers=auth,
        json={"kind": "search", "value": "needle"},
    ).json()
    assert [c["id"] for c in found["chats"]] == [target]
    assert "messages" not in found["chats"][0]


def test_scope_applies_before_counts_search_and_status(pagination_client, temp_db):
    client, headers = pagination_client
    shared = temp_db.create_chat("Shared needle", {})
    private = temp_db.create_chat("Private needle", {})
    auth = headers(chat_ids=[shared, "focal-suzent"])
    for query in [{}, {"kind": "search", "value": "needle"}]:
        page = client.post("/mobile/client/chat-page", headers=auth, json=query).json()
        assert page["total"] == 1
        assert [c["id"] for c in page["chats"]] == [shared]
    state = client.post(
        "/mobile/client/chat-status",
        headers=auth,
        json={"ids": [shared, private, "focal-suzent", "missing"]},
    ).json()
    assert [c["id"] for c in state["chats"]] == [shared]
    assert (
        client.get("/mobile/client/navigation", headers=auth).json()["regent"] is None
    )


def test_pins_independent_and_archived_hidden(pagination_client, temp_db):
    client, headers = pagination_client
    pinned = temp_db.create_chat("Pinned", {})
    temp_db.update_chat(pinned, pinned=True)
    archived = temp_db.create_chat("Archived", {})
    temp_db.update_chat(archived, archived=True)
    for index in range(31):
        temp_db.create_chat(f"New {index}", {})
    auth = headers(all_chats=True)
    page = client.post(
        "/mobile/client/chat-page", headers=auth, json={"kind": "pinned"}
    ).json()
    assert [c["id"] for c in page["chats"]] == [pinned]
    recent = client.post("/mobile/client/chat-page", headers=auth, json={}).json()
    assert recent["total"] == 31
    assert pinned not in {c["id"] for c in recent["chats"]}
    assert (
        client.get("/mobile/client/navigation", headers=auth).json()["regent"]["id"]
        == "focal-suzent"
    )


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"kind": "status"},
        {"value": "x" * 201},
    ],
)
def test_page_validation(pagination_client, query):
    client, headers = pagination_client
    assert (
        client.post(
            "/mobile/client/chat-page", headers=headers(all_chats=True), json=query
        ).status_code
        == 400
    )


def test_status_is_bounded(pagination_client):
    client, headers = pagination_client
    assert (
        client.post(
            "/mobile/client/chat-status",
            headers=headers(all_chats=True),
            json={"ids": [str(i) for i in range(101)]},
        ).status_code
        == 400
    )


def test_more_than_1000_and_project_counts_are_authorized(pagination_client, temp_db):
    from suzent.database.models import ChatModel

    client, headers = pagination_client
    project = temp_db.create_project("Paged project", "paged-project")
    with temp_db._session() as session:
        session.add_all(
            [
                ChatModel(
                    id=f"page-{i:04}",
                    title=f"Example {i}",
                    created_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
                    config={},
                    project_id=project,
                )
                for i in range(1005)
            ]
        )
        session.commit()
    auth = headers(all_chats=True)
    page = client.post(
        "/mobile/client/chat-page",
        headers=auth,
        json={"kind": "project", "value": project, "offset": 1000},
    ).json()
    assert page["total"] == 1005
    assert len(page["chats"]) == 5
    assert page["nextOffset"] is None
    metadata = client.get("/mobile/client/navigation", headers=auth).json()
    assert (
        next(p for p in metadata["projects"] if p["id"] == project)["chatCount"] == 1005
    )
    scoped = headers(chat_ids=["page-0000"])
    metadata = client.get("/mobile/client/navigation", headers=scoped).json()
    assert metadata["projects"] == [
        {"id": project, "name": "Paged project", "chatCount": 1}
    ]
    found = client.post(
        "/mobile/client/chat-page",
        headers=scoped,
        json={"kind": "project", "value": project},
    ).json()
    assert found["total"] == 1
    assert [c["id"] for c in found["chats"]] == ["page-0000"]


def test_search_treats_wildcards_as_literal_text(pagination_client, temp_db):
    client, headers = pagination_client
    target = temp_db.create_chat("100%_ready", {})
    temp_db.create_chat("Everything else", {})
    page = client.post(
        "/mobile/client/chat-page",
        headers=headers(all_chats=True),
        json={"kind": "search", "value": "%_"},
    ).json()
    assert [c["id"] for c in page["chats"]] == [target]
