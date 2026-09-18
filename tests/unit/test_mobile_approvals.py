"""Mobile decisions use authoritative desktop contracts without policy writes."""

import asyncio
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.mobile.client_api import client_routes
from suzent.mobile.pairing import ClientPermissions, PairingStore
from suzent.permissions.actions import build_approval_decision


@pytest.fixture
def approval_client(tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "clients.json")
    records = [
        {
            "approvalId": "approval-1",
            "toolCallId": "tool-1",
            "toolName": "read_file",
            "args": {"path": "README.md"},
            "decision": build_approval_decision(
                "read_file", {"path": "README.md"}
            ).model_dump(mode="json"),
        }
    ]
    chat = SimpleNamespace(config={"_pending_approvals": records}, agent_state=None)
    monkeypatch.setattr(
        "suzent.routes.permission_routes.get_database",
        lambda: SimpleNamespace(get_chat=lambda _: chat),
    )
    monkeypatch.setattr(
        "suzent.database.get_database", lambda: SimpleNamespace(get_chat=lambda _: chat)
    )
    from suzent.acp.permissions import ACPPermissionBroker

    broker = ACPPermissionBroker()
    monkeypatch.setattr("suzent.acp.permissions.get_permission_broker", lambda: broker)
    calls = []

    async def send(request):
        calls.append(await request.json())
        records.clear()
        return JSONResponse({"ok": True}, status_code=202)

    monkeypatch.setattr("suzent.routes.chat_routes.chat_send", send)
    app = Starlette(routes=client_routes)
    app.state.mobile_store = store
    app.add_middleware(AuthBoundaryMiddleware)
    with TestClient(app, client=("192.0.2.1", 1234)) as client:

        def authorize(**scope):
            invite = store.invite(
                permissions=ClientPermissions(chat_ids=["shared"], **scope)
            )
            pickup = store.claim(
                invite["pairing_id"],
                invite["invitation"],
                "Test phone",
                "ios",
                confirm_permissions=True,
            )
            result = store.collect(invite["pairing_id"], pickup["pickup_secret"])
            client.headers["Authorization"] = f"Bearer {result['token']}"
            return result["device"]["device_id"]

        yield SimpleNamespace(
            client=client,
            store=store,
            records=records,
            calls=calls,
            authorize=authorize,
            broker=broker,
        )


def decision(action="allow_once", **extra):
    return {
        "chat_id": "shared",
        "decisions": [
            {
                "chat_id": "shared",
                "request_id": "approval-1",
                "action_id": action,
                **extra,
            }
        ],
    }


def test_scoped_list_and_approval_grant(approval_client):
    f = approval_client
    f.authorize()
    assert f.client.get("/mobile/client/chats/private/approvals").status_code == 403
    pending = f.client.get("/mobile/client/chats/shared/approvals").json()["pending"]
    assert pending[0]["args"] == '{"path": "README.md"}'
    assert {a["id"] for a in pending[0]["actions"]} == {"allow_once", "reject"}
    assert f.client.post("/mobile/client/approvals", json=decision()).status_code == 403
    assert f.calls == []
    device = f.authorize(approve_tools=True)
    f.store.revoke(device)
    assert f.client.post("/mobile/client/approvals", json=decision()).status_code == 401


@pytest.mark.parametrize("action", ["allow_global", "allow_session", "invented"])
def test_policy_escalation_is_rejected(approval_client, action):
    f = approval_client
    f.authorize(approve_tools=True)
    assert (
        f.client.post("/mobile/client/approvals", json=decision(action)).status_code
        == 403
    )
    assert f.calls == []


@pytest.mark.parametrize(
    "extra",
    [
        {"remember": "global"},
        {"approved": True},
        {"args": {"path": "private"}},
        {"tool_name": "run_command"},
    ],
)
def test_untrusted_resume_fields_are_rejected(approval_client, extra):
    f = approval_client
    f.authorize(approve_tools=True)
    assert (
        f.client.post("/mobile/client/approvals", json=decision(**extra)).status_code
        == 400
    )
    assert f.calls == []


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("action,approved", [("allow_once", True), ("reject", False)])
def test_resume_uses_desktop_handler_and_only_once(
    approval_client, legacy, action, approved
):
    f = approval_client
    f.authorize(approve_tools=True)
    if legacy:
        f.records[0].pop("decision")
    assert (
        f.client.post("/mobile/client/approvals", json=decision(action)).status_code
        == 202
    )
    item = f.calls[0]["resume_approvals"][0]
    assert item["approved"] is approved
    assert item["remember"] == ""
    assert item["tool_call_id"] == "tool-1"
    assert ("action_id" in item) is not legacy
    assert (
        f.client.post("/mobile/client/approvals", json=decision(action)).status_code
        == 409
    )
    assert len(f.calls) == 1


def test_duplicate_and_partial_batches_do_not_resume(approval_client):
    f = approval_client
    f.authorize(approve_tools=True)
    body = decision()
    body["decisions"] *= 2
    assert f.client.post("/mobile/client/approvals", json=body).status_code == 409
    f.records.append(
        {**f.records[0], "approvalId": "approval-2", "toolCallId": "tool-2"}
    )
    assert f.client.post("/mobile/client/approvals", json=decision()).status_code == 409
    assert f.calls == []


def test_revocation_during_pending_read_is_rechecked(approval_client, monkeypatch):
    f = approval_client
    device = f.authorize(approve_tools=True)
    from suzent.mobile.approvals import pending_approvals

    async def revoke(request, chat_id):
        pending = await pending_approvals(request, chat_id)
        f.store.revoke(device)
        return pending

    monkeypatch.setattr("suzent.mobile.approvals.pending_approvals", revoke)
    assert f.client.post("/mobile/client/approvals", json=decision()).status_code == 401
    assert f.calls == []


def test_acp_resolves_existing_broker_once(approval_client):
    from suzent.acp.permissions import PendingPermission

    f = approval_client
    f.authorize(approve_tools=True)
    f.records.clear()

    async def add():
        future = asyncio.get_running_loop().create_future()
        f.broker._pending["approval-1"] = PendingPermission(
            "approval-1",
            "shared",
            "session",
            {"title": "Read fixture", "rawInput": {"path": "README.md"}},
            [
                {"optionId": "once", "kind": "allow_once"},
                {"optionId": "always", "kind": "allow_always"},
            ],
            future,
        )
        return future

    future = f.client.portal.call(add)
    result = f.client.get("/mobile/client/chats/shared/approvals").json()["pending"][0]
    assert {a["id"] for a in result["actions"]} == {"once", "__suzent_cancel__"}
    assert (
        f.client.post(
            "/mobile/client/approvals", json=decision("always", kind="acp")
        ).status_code
        == 403
    )
    assert (
        f.client.post(
            "/mobile/client/approvals", json=decision("once", kind="acp")
        ).status_code
        == 200
    )
    assert future.result()["outcome"]["optionId"] == "once"
    assert (
        f.client.post(
            "/mobile/client/approvals", json=decision("once", kind="acp")
        ).status_code
        == 409
    )
    assert f.calls == []
