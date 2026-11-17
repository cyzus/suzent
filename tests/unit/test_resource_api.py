"""The common API must never turn a paired grant into operator access."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import json

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.api.operations import OPERATIONS, Operation
from suzent.api.router import resource_routes
from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.mobile.pairing import ClientPermissions, PairingStore
from suzent.mobile.tls import MobileGateway


@pytest.fixture
def shared_app(tmp_path: Path) -> Starlette:
    app = Starlette(routes=resource_routes)
    app.state.mobile_store = PairingStore(tmp_path / "devices.json")
    app.add_middleware(AuthBoundaryMiddleware)
    return app


def token(app: Starlette, **permissions: object) -> str:
    store = app.state.mobile_store
    invite = store.invite()
    claim = store.claim(invite["pairing_id"], invite["invitation"], "Phone", "android")
    store.decide(invite["pairing_id"], ClientPermissions(**permissions))
    return store.collect(invite["pairing_id"], claim["pickup_secret"])["token"]


@pytest.mark.parametrize(
    "operation", [op for op in OPERATIONS if op.host_only], ids=lambda op: op.name
)
def test_host_operations_reject_even_fully_authorized_paired_devices(
    shared_app: Starlette, operation: Operation
) -> None:
    credential = token(
        shared_app,
        all_chats=True,
        send=True,
        stop=True,
        create_chats=True,
        manage_chats=True,
        approve_tools=True,
    )
    path = "/api/v1" + operation.path.replace("{chat_id}", "shared").replace(
        "{project_id}", "project"
    )
    with TestClient(shared_app) as client:
        response = client.request(
            operation.method,
            path,
            json={},
            headers={"Authorization": f"Bearer {credential}"},
        )
    assert response.status_code == 403


def test_common_capabilities_are_filtered_by_identity_and_require_auth(
    shared_app: Starlette,
) -> None:
    with TestClient(shared_app, client=("192.0.2.1", 1234)) as client:
        assert client.get("/api/v1/capabilities").status_code == 401
        credential = token(shared_app, chat_ids=["shared"])
        response = client.get(
            "/api/v1/capabilities", headers={"Authorization": f"Bearer {credential}"}
        )
        assert response.status_code == 200
        assert "models" in response.json()["operations"]
        assert "send" not in response.json()["operations"]
        assert "updateChat" not in response.json()["operations"]
    with TestClient(shared_app, client=("127.0.0.1", 1234)) as client:
        assert "updateChat" in client.get("/api/v1/capabilities").json()["operations"]
        assert (
            client.get(
                "/api/v1/capabilities", headers={"Authorization": "Bearer invalid"}
            ).status_code
            == 401
        )


@pytest.mark.parametrize("scope", ["node", "agent", "full"])
def test_remote_host_tokens_keep_their_scope_and_gateway_never_grants_host_access(
    shared_app: Starlette, scope: str
) -> None:
    shared_app.state.node_manager = SimpleNamespace(
        device_store=SimpleNamespace(
            verify=lambda value: {"scope": scope} if value == "host-token" else None
        )
    )
    headers = {"Authorization": "Bearer host-token"}
    with TestClient(shared_app, client=("192.0.2.1", 1234)) as client:
        assert client.get("/api/v1/capabilities", headers=headers).status_code == (
            200 if scope == "full" else 401
        )
    with TestClient(MobileGateway(shared_app), client=("127.0.0.1", 1234)) as client:
        assert client.get("/api/v1/capabilities", headers=headers).status_code == 401
        assert client.get("/api/v1/capabilities").status_code == 401
        credential = token(shared_app, send=True)
        assert (
            client.get(
                "/api/v1/capabilities",
                headers={"Authorization": f"Bearer {credential}"},
            ).status_code
            == 200
        )


def test_desktop_fields_reach_existing_service_but_device_fields_are_restricted(
    shared_app: Starlette, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    async def send(request: Request) -> JSONResponse:
        calls.append(await request.json())
        return JSONResponse({"chat_id": "shared"}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    payload = {
        "chat_id": "shared",
        "message": "hello",
        "config": {"model": "test/model"},
        "client_run_token": "run-1",
    }
    with TestClient(shared_app) as client:
        assert client.post("/api/v1/send", json=payload).status_code == 202
        assert calls == [payload]
        credential = token(shared_app, chat_ids=["shared"], send=True)
        assert (
            client.post(
                "/api/v1/send",
                json=payload,
                headers={"Authorization": f"Bearer {credential}"},
            ).status_code
            == 400
        )
    assert calls == [payload]


def test_desktop_stop_keeps_run_id_and_reason(
    shared_app: Starlette, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    async def stop(request: Request) -> JSONResponse:
        calls.append(await request.json())
        return JSONResponse({"stream_stopped": True})

    monkeypatch.setattr("suzent.routes.chat_routes.stop_chat", stop)
    payload = {"chat_id": "shared", "run_id": "run-1", "reason": "user"}
    with TestClient(shared_app) as client:
        response = client.post("/api/v1/stop", json=payload)
    assert response.json() == {"stream_stopped": True}
    assert calls == [payload]


def test_registry_schema_and_generated_transport_inventory_match() -> None:
    spec = json.loads(
        Path("packages/api-contract/openapi.json").read_text(encoding="utf-8")
    )
    identifiers = []
    for op in OPERATIONS:
        operation = spec["paths"]["/api/v1" + op.path][op.method.lower()]
        assert operation["operationId"] == op.name
        assert operation["x-host-only"] == op.host_only
        assert operation["x-actions"] == list(op.actions)
        identifiers.append(op.name)
    assert len(identifiers) == len(set(identifiers))


def test_host_operations_preserve_the_existing_desktop_http_methods() -> None:
    import ast

    tree = ast.parse(Path("src/suzent/server.py").read_text(encoding="utf-8"))
    methods_by_handler: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id != "Route"
        ):
            continue
        if len(node.args) < 2 or not isinstance(node.args[1], ast.Name):
            continue
        methods = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "methods"),
            None,
        )
        if isinstance(methods, ast.List):
            methods_by_handler.setdefault(node.args[1].id, set()).update(
                ast.literal_eval(methods)
            )
    for op in OPERATIONS:
        target = op.host_handler or (op.handler if op.host_only else "")
        name = target.split(".")[-1]
        if name in methods_by_handler:
            assert op.method in methods_by_handler[name], op.name


def test_runtime_schema_requires_authentication_and_matches_generated_contract(
    shared_app: Starlette,
) -> None:
    with TestClient(shared_app, client=("192.0.2.1", 1234)) as client:
        assert client.get("/api/v1/openapi.json").status_code == 401
        credential = token(shared_app)
        response = client.get(
            "/api/v1/openapi.json", headers={"Authorization": f"Bearer {credential}"}
        )
    assert response.status_code == 200
    assert response.json() == json.loads(
        Path("packages/api-contract/openapi.json").read_text(encoding="utf-8")
    )
