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
    records = {key: SimpleNamespace(id=key, title=key) for key in ("shared", "private")}
    db = SimpleNamespace(
        get_chat=records.get,
        list_chat_titles=lambda chat_ids, limit: [
            (record.id, record.title)
            for record in records.values()
            if chat_ids is None or record.id in chat_ids
        ][:limit],
    )
    monkeypatch.setattr("suzent.mobile.client_api.get_database", lambda: db)
    with TestClient(app, client=("192.0.2.1", 1234)) as client:
        yield client, store


def test_scoped_reads_and_host_endpoints(setup_client, monkeypatch):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"])
    client.headers["Authorization"] = f"Bearer {result['token']}"
    assert client.get("/mobile/client/chats").json()["chats"] == [
        {"id": "shared", "title": "shared", "isRunning": False}
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
    assert calls == [base]


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
    assert set(response.json()) == {"id", "title", "messages"}
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


def test_transcript_reports_current_run_without_loading_runtime(
    setup_client, monkeypatch
):
    client, store = setup_client
    result = grant(store, chat_ids=["shared"])
    client.headers["Authorization"] = f"Bearer {result['token']}"
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
