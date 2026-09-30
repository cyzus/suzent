import asyncio
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.mobile.client_api import client_routes, revocable_stream
from suzent.mobile.pairing import ClientPermissions, PairingStore
from suzent.routes.mobile_routes import mobile_routes


def grant(store, **permissions):
    invite = store.invite()
    pickup = store.claim(invite["pairing_id"], invite["invitation"], "Phone", "ios")
    store.decide(invite["pairing_id"], ClientPermissions(**permissions))
    return store.collect(invite["pairing_id"], pickup["pickup_secret"])


@pytest.fixture
def setup_client(tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "clients.json")
    app = Starlette(routes=[*mobile_routes, *client_routes])
    app.state.mobile_store = store
    app.add_middleware(AuthBoundaryMiddleware)
    records = {
        key: SimpleNamespace(id=key, title=key, config={}, state_revision=0)
        for key in ("shared", "private")
    }

    def update_chat(chat_id: str, **changes: object) -> bool:
        if chat_id not in records:
            return False
        for key, value in changes.items():
            setattr(records[chat_id], key, value)
        return True

    def merge_chat_config(chat_id: str, updates: dict[str, object]) -> bool:
        return update_chat(chat_id, config={**records[chat_id].config, **updates})

    db = SimpleNamespace(
        merge_chat_config=merge_chat_config,
        has_client_message=lambda chat_id, message_id: False,
        get_pinned_chat_ids=lambda ids: set(),
        get_subagent_chat_ids_for_parent_chat=lambda chat_id: [],
        update_chat=update_chat,
        get_chat=records.get,
        get_chat_projects=lambda ids: {
            key: ("p-" + key, key.title()) for key in ids if key in records
        },
        list_projects=lambda: [
            SimpleNamespace(id="p-shared", name="Shared"),
            SimpleNamespace(id="p-private", name="Private"),
        ],
        list_chat_titles=lambda chat_ids, limit: [
            (record.id, record.title)
            for record in records.values()
            if chat_ids is None or record.id in chat_ids
        ][:limit],
    )
    monkeypatch.setattr("suzent.mobile.client_api.get_database", lambda: db)
    monkeypatch.setattr(
        "suzent.core.providers.get_default_chat_model", lambda: "test/model"
    )
    monkeypatch.setattr(
        "suzent.core.providers.get_enabled_models_from_db",
        lambda: ["test/model", "test/other"],
    )
    with TestClient(app, client=("192.0.2.1", 1234)) as client:
        yield client, store


def test_scoped_reads_and_host_endpoints(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"])
    client.headers["Authorization"] = f"Bearer {result['token']}"
    assert client.get("/mobile/client/chats").json()["chats"] == [
        {
            "id": "shared",
            "title": "shared",
            "pinned": False,
            "isRunning": False,
            "projectId": "p-shared",
            "projectName": "Shared",
        }
    ]
    assert client.get("/mobile/client/chats/private").status_code == 403
    assert (
        client.post(
            "/mobile/client/send", json={"chat_id": "shared", "message": "hello"}
        ).status_code
        == 403
    )
    assert (
        client.post("/mobile/client/stop", json={"chat_id": "shared"}).status_code
        == 403
    )
    assert client.post("/mobile/client/chats", json={"title": "New"}).status_code == 403
    for path in ("/config", "/chats", "/mobile/devices", "/mobile/pairing/pending"):
        assert client.get(path).status_code == 401
    assert (
        client.get("/mobile/client/session").json()["device"]["permissions"]["send"]
        is False
    )
    store.revoke(result["device"]["device_id"])
    assert client.get("/mobile/client/session").status_code == 401


@pytest.mark.parametrize("action", ["pin", "unpin", "rename", "move", "delete"])
def test_management_requires_explicit_permission_and_scope(setup_client, action):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True, create_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    body = {"chat_id": "shared", "action": action, "value": "p-shared"}
    assert client.post("/mobile/client/manage", json=body).status_code == 403
    assert store.set_management(result["device"]["device_id"], True)
    body["chat_id"] = "private"
    assert client.post("/mobile/client/manage", json=body).status_code == 403
    assert (
        client.post(
            f"/mobile/devices/{result['device']['device_id']}/management",
            json={"enabled": True},
        ).status_code
        == 401
    )


def test_management_validation_and_revocation(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    for action in ("pin", "unpin", "rename"):
        assert (
            client.post(
                "/mobile/client/manage",
                json={"chat_id": "shared", "action": action, "value": "New title"},
            ).status_code
            == 200
        )
    for value in ("", "  ", "x" * 201):
        assert (
            client.post(
                "/mobile/client/manage",
                json={"chat_id": "shared", "action": "rename", "value": value},
            ).status_code
            == 400
        )
    assert (
        client.post(
            "/mobile/client/manage",
            json={"chat_id": "shared", "action": "pin", "config": {}},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/mobile/client/manage",
            json={"chat_id": "shared", "action": "move", "value": "p-private"},
        ).status_code
        == 403
    )
    monkeypatch.setattr(
        "suzent.core.stream_registry.is_background_streaming", lambda _: True
    )
    for action in ("move", "delete"):
        assert (
            client.post(
                "/mobile/client/manage",
                json={"chat_id": "shared", "action": action, "value": "p-shared"},
            ).status_code
            == 409
        )
    store.set_management(result["device"]["device_id"], False)
    assert (
        client.post(
            "/mobile/client/manage", json={"chat_id": "shared", "action": "pin"}
        ).status_code
        == 403
    )


def test_management_move_and_delete_do_not_escape_scope(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    calls = []

    async def handler(request):
        calls.append((request.path_params, request.query_params, await request.json()))
        return JSONResponse({"ok": True})

    monkeypatch.setattr("suzent.routes.project_routes.move_chat_to_project", handler)
    monkeypatch.setattr("suzent.routes.chat_routes.delete_chat", handler)
    assert (
        client.post(
            "/mobile/client/manage",
            json={"chat_id": "shared", "action": "move", "value": "p-shared"},
        ).status_code
        == 200
    )
    assert calls[-1][0] == {"chat_id": "shared"}
    assert calls[-1][2] == {"project_id": "p-shared"}
    assert (
        client.post(
            "/mobile/client/manage?cascade=true",
            json={"chat_id": "shared", "action": "delete"},
        ).status_code
        == 200
    )
    assert not calls[-1][1]

    from suzent.mobile.client_api import get_database

    monkeypatch.setattr(
        get_database(), "get_subagent_chat_ids_for_parent_chat", lambda _: ["private"]
    )
    assert (
        client.post(
            "/mobile/client/manage",
            json={"chat_id": "shared", "action": "move", "value": "p-shared"},
        ).status_code
        == 403
    )
    restored = PairingStore(store.path)
    assert restored.verify(result["token"]).permissions.manage_chats
    restored.set_management(result["device"]["device_id"], False)
    assert not PairingStore(store.path).verify(result["token"]).permissions.manage_chats


def test_move_rejects_running_shared_descendants(setup_client, monkeypatch):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared", "private"], manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    monkeypatch.setattr(
        get_database(), "get_subagent_chat_ids_for_parent_chat", lambda _: ["private"]
    )
    monkeypatch.setattr(
        "suzent.core.stream_registry.is_background_streaming",
        lambda chat_id: chat_id == "private",
    )
    assert (
        client.post(
            "/mobile/client/manage",
            json={"chat_id": "shared", "action": "move", "value": "p-shared"},
        ).status_code
        == 409
    )


def test_send_cannot_override_permissions_or_run_commands(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    calls = []

    async def send(request):
        calls.append(await request.json())
        return JSONResponse({"chat_id": "shared"}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    base = {"chat_id": "shared", "message": "hello"}
    for extra in (
        {"config": {"permission_mode": "auto"}},
        {"resume_approvals": [{}]},
        {"files": ["/etc/passwd"]},
    ):
        assert (
            client.post("/mobile/client/send", json={**base, **extra}).status_code
            == 400
        )
    assert (
        client.post(
            "/mobile/client/send", json={**base, "message": "/anything"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/mobile/client/send", json={**base, "chat_id": "private"}
        ).status_code
        == 403
    )
    assert calls == []
    assert client.post("/mobile/client/send", json=base).status_code == 202
    assert calls == [{**base, "config": {"model": "test/model"}}]

    identified = {**base, "client_message_id": "phone-send-1"}
    assert client.post("/mobile/client/send", json=identified).status_code == 202
    assert calls[-1] == {**identified, "config": {"model": "test/model"}}


def test_created_chat_added_to_only_its_device(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, create_chats=True)
    other = grant(store, create_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"

    async def create(request):
        assert await request.json() == {"title": "Mobile"}
        return JSONResponse(
            {"id": "new", "title": "Mobile", "config": {"secret": "hidden"}},
            status_code=201,
        )

    monkeypatch.setattr("suzent.routes.chat_routes.create_chat", create)
    assert (
        client.post(
            "/mobile/client/chats", json={"title": "Mobile", "config": {}}
        ).status_code
        == 400
    )
    response = client.post("/mobile/client/chats", json={"title": "Mobile"})
    assert response.status_code == 201
    assert "config" not in response.json()
    assert store.verify(result["token"]).permissions.permits_chat("new")
    assert not store.verify(other["token"]).permissions.permits_chat("new")


@pytest.mark.asyncio
async def test_revocation_closes_idle_stream_and_cleans_subscription(tmp_path):
    store = PairingStore(tmp_path / "clients.json")
    result = grant(store, chat_ids=["shared"])
    closed = asyncio.Event()

    async def source():
        try:
            yield "first"
            await asyncio.Event().wait()
        finally:
            closed.set()

    stream = revocable_stream(source(), store, result["token"], "shared")
    assert await anext(stream) == "first"
    next_chunk = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    store.revoke(result["device"]["device_id"])
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(next_chunk, timeout=1)
    assert closed.is_set()


def test_transcript_excludes_backend_configuration(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"])
    client.headers["Authorization"] = f"Bearer {result['token']}"

    async def detail(request, *, include_runtime=True):
        assert include_runtime is False
        assert request.path_params["chat_id"] == "shared"
        return JSONResponse(
            {
                "id": "shared",
                "title": "Test",
                "messages": [{"role": "assistant", "content": "Visible transcript"}],
                "config": {"private": "must not be returned"},
                "agent_state": "internal",
            }
        )

    monkeypatch.setattr("suzent.routes.chat_routes.get_chat", detail)
    response = client.get("/mobile/client/chats/shared")
    assert response.status_code == 200
    assert set(response.json()) == {
        "pinned",
        "id",
        "title",
        "messages",
        "projectId",
        "projectName",
        "model",
        "models",
    }
    assert (
        client.post("/mobile/client/live", json={"chat_id": "private"}).status_code
        == 403
    )


def test_loopback_is_not_a_mobile_credential(tmp_path):
    app = Starlette(routes=client_routes)
    app.state.mobile_store = PairingStore(tmp_path / "clients.json")
    app.add_middleware(AuthBoundaryMiddleware)
    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        assert client.get("/mobile/client/session").status_code == 401
        assert client.get("/mobile/client/chats").status_code == 401


def test_corrupt_store_fails_without_exposing_records(tmp_path, monkeypatch):
    (tmp_path / "mobile_clients.json").write_text(
        '{"hash":{"display_name":"private-name"}}'
    )
    monkeypatch.setattr("suzent.routes.mobile_routes.USER_CONFIG_DIR", tmp_path)
    app = Starlette(debug=True, routes=client_routes)
    app.add_middleware(AuthBoundaryMiddleware)
    with TestClient(app, client=("192.0.2.1", 1234)) as client:
        response = client.get("/mobile/client/session")
        assert response.status_code == 503
        assert "private-name" not in response.text


@pytest.mark.parametrize("runtime", ["native", "acp"])
@pytest.mark.parametrize("model_key", ["model", "subagent_model"])
def test_transcript_reports_current_run_without_loading_runtime(
    setup_client, monkeypatch, runtime, model_key
):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"])
    client.headers["Authorization"] = f"Bearer {result['token']}"
    from suzent.mobile.client_api import get_database

    get_database().get_chat("shared").config = {
        model_key: "test/other",
        "runtime": runtime,
        "private": "hidden",
    }
    record = SimpleNamespace(
        model_dump=lambda **kwargs: {
            "id": "shared",
            "title": "Test",
            "messages": [],
            "config": {"private": "hidden"},
        }
    )
    monkeypatch.setattr(
        "suzent.routes.chat_routes.get_database",
        lambda: SimpleNamespace(get_chat=lambda _: record),
    )
    monkeypatch.setattr("suzent.core.retry.load_retry_checkpoint", lambda _: None)
    for running in (True, False):
        monkeypatch.setattr(
            "suzent.routes.chat_routes.is_background_streaming", lambda _: running
        )
        response = client.get("/mobile/client/chats/shared")
        assert response.status_code == 200
        assert response.json() == {
            "id": "shared",
            "title": "Test",
            "messages": [],
            "isRunning": running,
            "pinned": False,
            "projectId": "p-shared",
            "projectName": "Shared",
            "model": "test/other" if runtime == "native" else None,
            "models": ["test/model", "test/other"] if runtime == "native" else [],
        }


def test_phone_confirmation_routes_keep_authorization_on_desktop(setup_client):
    client, store = setup_client
    scope = ClientPermissions(chat_ids=["shared"], send=True).model_dump()
    assert (
        client.post("/mobile/pairing/invite", json={"permissions": scope}).status_code
        == 401
    )
    with TestClient(client.app, client=("127.0.0.1", 4321)) as desktop:
        response = desktop.post("/mobile/pairing/invite", json={"permissions": scope})
        assert response.status_code == 201
        invite = response.json()
        assert invite["approval"] == "phone"
        preview = client.post(
            "/mobile/pairing/preview", json={"pairing_id": invite["pairing_id"]}
        )
        assert preview.status_code == 200
        assert preview.json()["permissions"] == scope
        assert preview.headers["cache-control"] == "no-store"
        assert (
            client.post(
                f"/mobile/pairing/{invite['pairing_id']}/cancel", json={}
            ).status_code
            == 401
        )
        body = {
            "pairing_id": invite["pairing_id"],
            "invitation": invite["invitation"],
            "display_name": "Test phone",
            "platform": "android",
        }
        assert (
            client.post(
                "/mobile/pairing/claim",
                json={**body, "permissions": {"all_chats": True}},
            ).status_code
            == 400
        )
        assert client.post("/mobile/pairing/claim", json=body).status_code == 400
        body["confirm_permissions"] = True
        pickup = client.post("/mobile/pairing/claim", json=body).json()
        result = client.post(
            "/mobile/pairing/collect",
            json={
                "pairing_id": invite["pairing_id"],
                "pickup_secret": pickup["pickup_secret"],
            },
        ).json()
        assert result["status"] == "approved"
        assert result["device"]["permissions"] == scope
        client.headers["Authorization"] = f"Bearer {result['token']}"
        assert client.get("/mobile/client/chats/private").status_code == 403
        assert (
            client.post("/mobile/client/stop", json={"chat_id": "shared"}).status_code
            == 403
        )
        assert (
            desktop.post(
                f"/mobile/devices/{result['device']['device_id']}/revoke", json={}
            ).status_code
            == 200
        )
        assert client.get("/mobile/client/session").status_code == 401
        next_invite = desktop.post(
            "/mobile/pairing/invite", json={"permissions": scope}
        ).json()
        assert (
            desktop.post(
                f"/mobile/pairing/{next_invite['pairing_id']}/cancel", json={}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/mobile/pairing/preview",
                json={"pairing_id": next_invite["pairing_id"]},
            ).status_code
            == 400
        )


def test_projects_respect_chat_scope(setup_client):
    client, store = setup_client
    for permissions, expected in [
        ({"chat_ids": ["shared"]}, ["p-shared"]),
        ({"all_chats": True}, ["p-shared", "p-private"]),
        ({}, []),
    ]:
        result = grant(store, **permissions)
        client.headers["Authorization"] = f"Bearer {result['token']}"
        response = client.get("/mobile/client/projects")
        assert response.status_code == 200
        assert [project["id"] for project in response.json()["projects"]] == expected
        store.revoke(result["device"]["device_id"])
        assert client.get("/mobile/client/projects").status_code == 401


def test_create_in_shared_project_only(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], create_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    calls = []

    async def create(request):
        calls.append(await request.json())
        return JSONResponse({"id": "new", "title": "Mobile"}, status_code=201)

    monkeypatch.setattr("suzent.routes.chat_routes.create_chat", create)
    assert (
        client.post(
            "/mobile/client/chats", json={"project_id": "p-private"}
        ).status_code
        == 403
    )
    assert calls == []
    body = {"project_id": "p-shared", "title": "Mobile"}
    assert client.post("/mobile/client/chats", json=body).status_code == 201
    assert calls == [body]
    assert store.verify(result["token"]).permissions.permits_chat("new")


def test_model_selection_only_forwards_enabled_native_model(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    calls = []

    async def send(request):
        calls.append(await request.json())
        return JSONResponse({"chat_id": "shared"}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    body = {"chat_id": "shared", "message": "Hello", "model": "test/other"}
    assert (
        client.post(
            "/mobile/client/send", json={**body, "model": "disabled/model"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/mobile/client/send", json={**body, "chat_id": "private"}
        ).status_code
        == 403
    )
    assert calls == []
    assert client.post("/mobile/client/send", json=body).status_code == 202
    assert calls == [
        {"chat_id": "shared", "message": "Hello", "config": {"model": "test/other"}}
    ]
    from suzent.mobile.client_api import get_database

    get_database().get_chat("shared").config = {"runtime": "acp"}
    assert client.post("/mobile/client/send", json=body).status_code == 400
    assert len(calls) == 1


def test_composer_does_not_create_or_list_chats(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, create_chats=True, send=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"

    def unexpected_database_access():
        pytest.fail("Opening an empty composer must not access stored conversations")

    monkeypatch.setattr(
        "suzent.mobile.client_api.get_database", unexpected_database_access
    )
    for _ in range(2):
        response = client.get("/mobile/client/composer")
        assert response.status_code == 200
        assert response.json() == {
            "id": "",
            "title": "",
            "messages": [],
            "model": "test/model",
            "models": ["test/model", "test/other"],
        }
    assert store.verify(result["token"]).permissions.chat_ids == []
    store.revoke(result["device"]["device_id"])
    assert client.get("/mobile/client/composer").status_code == 401


def test_confirm_pairing_requires_mobile_credential(setup_client):
    client, store = setup_client
    assert client.post("/mobile/client/pairing/confirm", json={}).status_code == 401
    result = grant(store, chat_ids=["shared"])
    client.headers["Authorization"] = f"Bearer {result['token']}"
    assert client.post("/mobile/client/pairing/confirm", json={}).status_code == 200
    store.revoke(result["device"]["device_id"])
    assert client.post("/mobile/client/pairing/confirm", json={}).status_code == 401


@pytest.mark.parametrize("status", [202, 409, 500])
def test_send_preserves_chat_config_and_saves_only_accepted_model(
    setup_client, monkeypatch, status
):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    db = get_database()
    original = {"model": "test/model", "tools": [], "permission_mode": "default"}
    db.get_chat("shared").config = dict(original)
    calls = []

    async def send(request):
        calls.append(await request.json())
        return JSONResponse({}, status_code=status)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    body = {"chat_id": "shared", "message": "Hello", "model": "test/other"}
    assert client.post("/mobile/client/send", json=body).status_code == status
    expected = {**original, "model": "test/other"}
    assert calls[0]["config"] == expected
    assert db.get_chat("shared").config == (expected if status == 202 else original)

    # Returning to this conversation and sending without an override must use
    # its saved model, not global preferences, and retain its tool settings.
    client.post("/mobile/client/send", json={"chat_id": "shared", "message": "Again"})
    assert calls[-1]["config"] == (expected if status == 202 else original)


def test_duplicate_mobile_send_does_not_replace_saved_model(setup_client, monkeypatch):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    db = get_database()
    db.get_chat("shared").config = {"model": "test/model"}
    db.has_client_message = lambda *_: True

    async def send(request):
        return JSONResponse({}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    response = client.post(
        "/mobile/client/send",
        json={
            "chat_id": "shared",
            "message": "Hello",
            "model": "test/other",
            "client_message_id": "already-accepted",
        },
    )
    assert response.status_code == 202
    assert db.get_chat("shared").config == {"model": "test/model"}


@pytest.mark.parametrize(
    "config",
    [
        {"subagent_model": "test/other"},
        {"subagent_model": "test/model", "model": "test/other"},
    ],
)
def test_mobile_send_uses_subagent_model_unless_explicitly_changed(
    setup_client, monkeypatch, config
):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    get_database().get_chat("shared").config = dict(config)
    calls = []

    async def send(request):
        calls.append(await request.json())
        return JSONResponse({}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    assert (
        client.post(
            "/mobile/client/send", json={"chat_id": "shared", "message": "Hello"}
        ).status_code
        == 202
    )
    assert calls[0]["config"]["model"] == "test/other"
    assert get_database().get_chat("shared").config["model"] == "test/other"


@pytest.mark.parametrize("action", ["retry", "edit", "fork"])
def test_message_actions_require_scoped_permissions(setup_client, action):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"])
    client.headers["Authorization"] = f"Bearer {result['token']}"
    from suzent.mobile.client_api import get_database

    get_database().get_chat("shared").messages = [{"role": "user", "content": "Hi"}]
    body = {"chat_id": "shared", "message_index": 0, "action": action, "text": "Edited"}
    assert client.post("/mobile/client/message-action", json=body).status_code == 403
    assert (
        client.post(
            "/mobile/client/message-action", json={**body, "chat_id": "private"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "action,expected", [("retry", "/retry"), ("edit", "/retry-edit Updated")]
)
def test_message_actions_replay_only_latest_turn(
    setup_client, monkeypatch, action, expected
):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True, manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    from suzent.mobile.client_api import get_database

    record = get_database().get_chat("shared")
    record.messages = [
        {"role": "user", "content": "Earlier"},
        {"role": "user", "content": "Latest"},
    ]
    record.config = {"model": "test/other"}
    monkeypatch.setattr(
        "suzent.core.retry.load_retry_checkpoint",
        lambda _: SimpleNamespace(
            user_message=record.messages[-1]["content"],
            config_snapshot={"_retry_revision": 0},
        ),
    )
    calls = []

    async def send(request):
        calls.append(await request.json())
        return JSONResponse({"chat_id": "shared"}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    body = {
        "chat_id": "shared",
        "message_index": 0,
        "action": action,
        "text": "Updated",
    }
    assert client.post("/mobile/client/message-action", json=body).status_code == 409
    assert not calls
    assert (
        client.post(
            "/mobile/client/message-action", json={**body, "message_index": 1}
        ).status_code
        == 202
    )
    assert calls == [
        {
            "chat_id": "shared",
            "message": expected,
            "config": {"model": "test/other", "_retry_expected_revision": 0},
        }
    ]
    monkeypatch.setattr(
        "suzent.core.stream_registry.is_background_streaming", lambda _: True
    )
    assert (
        client.post(
            "/mobile/client/message-action", json={**body, "message_index": 1}
        ).status_code
        == 409
    )
    assert len(calls) == 1


@pytest.mark.parametrize("tool_continuation", [False, True])
def test_mobile_message_fork_grants_access_only_to_requesting_device(
    setup_client, monkeypatch, tool_continuation
):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"], create_chats=True)
    other = grant(store, chat_ids=["shared"], create_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    from suzent.mobile.client_api import get_database

    messages = [
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Answer"},
    ]
    if tool_continuation:
        messages[-1]["tool_calls"] = [{"id": "call-1"}]
        messages.extend(
            [
                {"role": "tool", "content": "Tool result", "tool_call_id": "call-1"},
                {"role": "assistant", "content": "Final answer"},
            ]
        )
    expected_boundary = len(messages)
    messages.extend(
        [
            {"role": "user", "content": "Next turn"},
            {"role": "assistant", "content": "Next answer"},
        ]
    )
    get_database().get_chat("shared").messages = messages
    calls = []

    def fork(chat_id, *, message_index):
        from suzent.core.fork import _validate_assistant_message_boundary

        _validate_assistant_message_boundary(messages, message_index)
        calls.append((chat_id, message_index))
        return "forked", []

    monkeypatch.setattr("suzent.core.fork.fork_chat", fork)
    response = client.post(
        "/mobile/client/message-action",
        json={"chat_id": "shared", "message_index": 1, "action": "fork"},
    )
    assert response.json() == {"chat_id": "forked"}
    assert calls == [("shared", expected_boundary)]
    assert store.verify(result["token"]).permissions.permits_chat("forked")
    assert not store.verify(other["token"]).permissions.permits_chat("forked")


@pytest.mark.parametrize(
    "override,expected_status",
    [
        ({"text": "  /model unwanted"}, 403),
        ({"model": "disabled/model"}, 400),
        ({"model": "test/other"}, 202),
    ],
)
def test_message_edit_checks_commands_and_model(
    setup_client, monkeypatch, override, expected_status
):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True, manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    record = get_database().get_chat("shared")
    record.messages = [{"role": "user", "content": "Question"}]
    record.config = {"model": "test/model"}
    monkeypatch.setattr(
        "suzent.core.retry.load_retry_checkpoint",
        lambda _: SimpleNamespace(
            user_message=record.messages[-1]["content"],
            config_snapshot={"_retry_revision": 0},
        ),
    )
    calls = []

    async def send(request):
        calls.append(await request.json())
        return JSONResponse({"chat_id": "shared"}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    response = client.post(
        "/mobile/client/message-action",
        json={
            "chat_id": "shared",
            "message_index": 0,
            "action": "edit",
            "text": "Updated",
            **override,
        },
    )
    assert response.status_code == expected_status
    if expected_status == 202:
        assert calls[0]["config"]["model"] == "test/other"
        assert record.config["model"] == "test/other"
    else:
        assert not calls
        assert record.config["model"] == "test/model"


def test_mobile_retry_rejects_acp_runtime(setup_client):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True, manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    record = get_database().get_chat("shared")
    record.messages = [{"role": "user", "content": "Question"}]
    record.config = {"runtime": "acp"}
    assert (
        client.post(
            "/mobile/client/message-action",
            json={"chat_id": "shared", "message_index": 0, "action": "retry"},
        ).status_code
        == 400
    )


@pytest.mark.parametrize("trigger", ["system_triggered", "trigger", "assistant", None])
@pytest.mark.parametrize("action", ["retry", "edit"])
def test_mobile_replay_rejects_automation_or_stale_checkpoint(
    setup_client, monkeypatch, trigger, action
):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True, manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    record = get_database().get_chat("shared")
    record.messages = [
        {"role": "user", "content": "Human prompt"},
        {"role": "assistant", "content": "Answer"},
    ]
    if trigger == "assistant":
        record.messages.append(
            {"role": "assistant", "content": "Autonomous goal result"}
        )
    elif trigger:
        record.messages.extend(
            [
                {"role": trigger, "content": "Scheduled task"},
                {"role": "assistant", "content": "Automation result"},
            ]
        )
    checkpoint = SimpleNamespace(
        user_message="Human prompt" if trigger else "Older prompt",
        config_snapshot={"_retry_revision": 0},
    )
    monkeypatch.setattr("suzent.core.retry.load_retry_checkpoint", lambda _: checkpoint)

    async def send(request):
        pytest.fail("A stale retry checkpoint must never be applied")

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    response = client.post(
        "/mobile/client/message-action",
        json={
            "chat_id": "shared",
            "message_index": 0 if action == "edit" else len(record.messages) - 1,
            "action": action,
            "text": "Edited prompt",
        },
    )
    assert response.status_code == 409


def test_mobile_retry_allows_one_complete_tool_turn(setup_client, monkeypatch):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True, manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    record = get_database().get_chat("shared")
    record.messages = [
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Working", "tool_calls": [{"id": "tool-1"}]},
        {"role": "tool", "content": "Result", "tool_call_id": "tool-1"},
        {"role": "assistant", "content": "Final answer"},
    ]
    monkeypatch.setattr(
        "suzent.core.retry.load_retry_checkpoint",
        lambda _: SimpleNamespace(
            user_message="Question", config_snapshot={"_retry_revision": 0}
        ),
    )

    async def send(request):
        return JSONResponse({"chat_id": "shared"}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    response = client.post(
        "/mobile/client/message-action",
        json={"chat_id": "shared", "message_index": 3, "action": "retry"},
    )
    assert response.status_code == 202


@pytest.mark.parametrize("checkpoint_revision", [None, 0])
@pytest.mark.parametrize("action", ["retry", "edit"])
def test_mobile_replay_rejects_hidden_state_changes(
    setup_client, monkeypatch, checkpoint_revision, action
):
    from suzent.mobile.client_api import get_database

    client, store = setup_client
    result = grant(store, chat_ids=["shared"], send=True, manage_chats=True)
    client.headers["Authorization"] = f"Bearer {result['token']}"
    record = get_database().get_chat("shared")
    record.state_revision = 1
    record.messages = [
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Answer"},
    ]
    snapshot = (
        {} if checkpoint_revision is None else {"_retry_revision": checkpoint_revision}
    )
    monkeypatch.setattr(
        "suzent.core.retry.load_retry_checkpoint",
        lambda _: SimpleNamespace(user_message="Question", config_snapshot=snapshot),
    )

    async def send(request):
        pytest.fail("A transcript-hidden state change must invalidate replay")

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    response = client.post(
        "/mobile/client/message-action",
        json={
            "chat_id": "shared",
            "message_index": 0 if action == "edit" else 1,
            "action": action,
            "text": "Edited",
        },
    )
    assert response.status_code == 409
