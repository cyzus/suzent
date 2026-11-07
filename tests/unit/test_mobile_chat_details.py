from datetime import datetime
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.mobile.chat_details import chat_detail_routes
from suzent.mobile.client_api import client_routes
from suzent.mobile.pairing import ClientPermissions, PairingStore
from suzent.routes.mobile_routes import mobile_routes


def grant(store, **permissions):
    invite = store.invite()
    pickup = store.claim(invite["pairing_id"], invite["invitation"], "Phone", "ios")
    store.decide(invite["pairing_id"], ClientPermissions(**permissions))
    return store.collect(invite["pairing_id"], pickup["pickup_secret"])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "clients.json")
    app = Starlette(routes=[*mobile_routes, *chat_detail_routes, *client_routes])
    app.state.mobile_store = store
    app.add_middleware(AuthBoundaryMiddleware)
    workspace = tmp_path / "projects" / "default"
    (workspace / "uploads").mkdir(parents=True)
    (workspace / "uploads" / "photo.png").write_bytes(b"png")
    (workspace / "notes.md").write_text("hello", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    (workspace / "escape").symlink_to(tmp_path / "secret.txt")
    records = {
        key: SimpleNamespace(
            id=key,
            config={"permission_mode": "auto"} if key == "shared" else {},
            context_usage={"context_tokens": 1200},
            created_at=datetime(2026, 11, 1),
        )
        for key in ("shared", "private", "child")
    }
    db = SimpleNamespace(
        get_chat=records.get,
        get_chat_projects=lambda ids: {key: ("p1", "Project") for key in ids},
        get_goal=lambda project_id, chat_id: SimpleNamespace(
            objective="Ship it", status="active", turns_elapsed=2, max_turns=10
        ),
        list_tasks=lambda **_: [
            SimpleNamespace(
                id=2, title="Test", status="completed", blocked_by=[], active_form=None
            ),
            SimpleNamespace(
                id=1, title="Write", status="pending", blocked_by=[3], active_form=None
            ),
        ],
        list_subagent_task_records=lambda parent_chat_id, limit: [
            {
                "task_id": "t1",
                "chat_id": "child",
                "description": "Research",
                "status": "completed",
                "started_at": "2026-11-01T10:00:00",
                "finished_at": "2026-11-01T10:05:00",
            }
        ],
        get_memory_recall=lambda chat_id: SimpleNamespace(
            items=[{"id": "m", "content": "Likes tea", "category": "preference"}]
        ),
        get_project_dir=lambda chat_id: workspace,
    )
    monkeypatch.setattr("suzent.mobile.chat_details.get_database", lambda: db)
    monkeypatch.setattr("suzent.mobile.client_api.get_database", lambda: db)
    monkeypatch.setattr("suzent.core.subagent_runner.list_all_tasks", lambda **_: [])
    monkeypatch.setattr("suzent.memory.lifecycle.get_memory_manager", lambda: None)
    monkeypatch.setattr(
        "suzent.core.providers.get_default_chat_model", lambda: "test/model"
    )
    monkeypatch.setattr(
        "suzent.core.context_compressor.resolve_context_limit", lambda model: 10000
    )
    with TestClient(app, client=("192.0.2.1", 1234)) as client:
        yield client, store


def authed(client, store, **permissions):
    client.headers["Authorization"] = f"Bearer {grant(store, **permissions)['token']}"


def test_details_for_a_full_control_phone(setup):
    client, store = setup
    authed(client, store, all_chats=True, approve_tools=True)
    body = client.get("/mobile/client/chats/shared/details").json()
    assert body["permissionMode"] == {
        "mode": "auto",
        "available": ["default", "auto", "full_access"],
        "canChange": True,
    }
    assert body["context"] == {"tokens": 1200, "limit": 10000}
    assert body["goal"]["objective"] == "Ship it"
    assert [task["status"] for task in body["tasks"]] == ["blocked", "completed"]
    assert [task["title"] for task in body["tasks"]] == ["Write", "Test"]
    assert body["agents"][0]["chatId"] == "child"
    assert body["memory"] == {
        "recalled": [{"content": "Likes tea", "category": "preference"}],
        "saved": [],
    }
    assert body["files"] is True


def test_selected_chats_see_no_workspace_memory_or_unshared_agents(setup):
    client, store = setup
    authed(client, store, chat_ids=["shared"])
    body = client.get("/mobile/client/chats/shared/details").json()
    assert body["memory"] is None
    assert body["files"] is False
    assert body["permissionMode"]["canChange"] is False
    assert body["agents"][0]["chatId"] is None
    assert client.get("/mobile/client/chats/private/details").status_code == 403
    assert client.get("/mobile/client/chats/shared/files").status_code == 403
    assert (
        client.get("/mobile/client/chats/shared/file?path=notes.md").status_code == 403
    )


def test_files_stay_inside_the_workspace(setup):
    client, store = setup
    authed(client, store, all_chats=True)
    root = client.get("/mobile/client/chats/shared/files").json()
    assert [entry["name"] for entry in root["entries"]][:1] == ["uploads"]
    assert root["path"] == ""
    uploads = client.get("/mobile/client/chats/shared/files?path=uploads").json()
    assert uploads["entries"][0]["name"] == "photo.png"
    response = client.get("/mobile/client/chats/shared/file?path=uploads/photo.png")
    assert response.status_code == 200
    assert response.content == b"png"
    assert response.headers["content-type"] == "image/png"
    for bad in ("../secret.txt", "uploads/../../secret.txt"):
        assert (
            client.get(f"/mobile/client/chats/shared/file?path={bad}").status_code
            == 400
        )
    assert client.get("/mobile/client/chats/shared/file?path=escape").status_code == 403
    assert (
        client.get("/mobile/client/chats/shared/files?path=notes.md").status_code == 400
    )


def test_permission_mode_requires_approval_grant(setup, monkeypatch):
    client, store = setup
    calls = []

    async def desktop_set_mode(request):
        calls.append((request.path_params["chat_id"], await request.json()))
        return JSONResponse({"mode": "full_access"})

    monkeypatch.setattr(
        "suzent.routes.chat_routes.set_permission_mode", desktop_set_mode
    )
    authed(client, store, all_chats=True, send=True)
    body = {"chat_id": "shared", "mode": "full_access"}
    assert client.post("/mobile/client/permission-mode", json=body).status_code == 403
    authed(client, store, all_chats=True, approve_tools=True)
    for invalid in ({**body, "mode": "plan"}, {**body, "restorePrevious": True}):
        assert (
            client.post("/mobile/client/permission-mode", json=invalid).status_code
            == 400
        )
    response = client.post("/mobile/client/permission-mode", json=body)
    assert response.json() == {"mode": "full_access"}
    assert calls == [("shared", {"mode": "full_access"})]
    regent = {"chat_id": "focal-suzent", "mode": "auto"}
    assert client.post("/mobile/client/permission-mode", json=regent).status_code == 403
