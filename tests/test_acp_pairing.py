"""Inbound authorization lifecycle and local approval boundary."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.applications import Starlette

from suzent.acp import login, pairing
from suzent.routes.acp_pairing_routes import acp_pairing_routes

SECRET = "a" * 43


def test_pairing_persistence_revocation_and_token_proof(tmp_path):
    store = pairing.ACPPairingStore(tmp_path / "grants.json")
    pending = store.begin("Editor", SECRET)
    assert store.verify(SECRET) is None
    with pytest.raises(ValueError):
        store.collect(pending["request_id"], "wrong")
    store.decide(pending["request_id"], True)
    assert store.collect(pending["request_id"], SECRET) == {"status": "approved"}
    grant = store.verify(SECRET)
    assert grant.expires_at is None
    assert SECRET not in store.path.read_text()
    restored = pairing.ACPPairingStore(store.path)
    assert restored.verify(SECRET) == grant
    with pytest.raises(ValueError):
        restored.begin("Another editor", SECRET)
    store.revoke(grant.grant_id)
    assert store.verify(SECRET) is None
    with pytest.raises(ValueError):
        store.collect(pending["request_id"], SECRET)


def test_expired_uncollected_approval_and_cancel(tmp_path, monkeypatch):
    now = 1000.0
    monkeypatch.setattr(pairing.time, "time", lambda: now)
    store = pairing.ACPPairingStore(tmp_path / "grants.json")
    request = store.begin("Editor", SECRET)
    store.decide(request["request_id"], True)
    now += 301
    assert store.verify(SECRET) is None
    assert store.pending() == []
    with pytest.raises(ValueError):
        store.collect(request["request_id"], SECRET)
    request = store.begin("Other", "b" * 43)
    store.decide(request["request_id"], True)
    store.cancel(request["request_id"], "b" * 43)
    assert store.verify("b" * 43) is None


@pytest.mark.asyncio
async def test_http_pairing_flow(tmp_path):
    app = Starlette(routes=acp_pairing_routes)
    app.state.acp_pairing = pairing.ACPPairingStore(tmp_path / "grants.json")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    headers = {"Authorization": f"Bearer {SECRET}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:
        assert (
            await client.post("/acp/auth/verify", headers=headers)
        ).status_code == 401
        response = await client.post(
            "/acp/auth/pair", json={"client_name": "Editor"}, headers=headers
        )
        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        request_id = response.json()["request_id"]
        path = f"/acp/auth/requests/{request_id}"
        assert (
            await client.post(path + "/decide", json={"approved": "false"})
        ).status_code == 400
        assert (
            await client.post(path + "/decide", json={"approved": True})
        ).status_code == 200
        assert (await client.post(path + "/collect", headers=headers)).json()[
            "status"
        ] == "approved"
        grant = (await client.post("/acp/auth/verify", headers=headers)).json()[
            "grant_id"
        ]
        assert SECRET not in (await client.get("/acp/auth/status")).text
        await client.delete(f"/acp/auth/grants/{grant}")
        assert (
            await client.post("/acp/auth/verify", headers=headers)
        ).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remote,host,origin",
    [
        ("192.0.2.1", "localhost", None),
        ("127.0.0.1", "attacker.example", None),
        ("127.0.0.1", "localhost", "https://attacker.example"),
        ("127.0.0.1", "localhost", "null"),
    ],
)
async def test_approval_rejects_remote_or_untrusted_browser(
    tmp_path, remote, host, origin
):
    app = Starlette(routes=acp_pairing_routes)
    app.state.acp_pairing = pairing.ACPPairingStore(tmp_path / "grants.json")
    transport = httpx.ASGITransport(app=app, client=(remote, 1234))
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://{host}"
    ) as client:
        result = await client.get(
            "/acp/auth/status", headers={"Origin": origin} if origin else {}
        )
        assert result.status_code == 403


def test_credential_roundtrip_and_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "credential.json"
    monkeypatch.setattr(login, "credential_path", lambda *_: path)
    login.save_credential(path, SECRET)
    assert login.load_credential("http://localhost", "Editor") == SECRET
    for malformed in ["invalid", "[]", "null", json.dumps({"dpapi": "bad"})]:
        path.write_text(malformed)
        assert login.load_credential("http://localhost", "Editor") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("decision,expected", [("approved", 0), ("denied", 1)])
async def test_terminal_login_exit_and_cleanup(
    tmp_path, monkeypatch, decision, expected
):
    client = AsyncMock()
    client.base_url = "http://localhost:25314"
    client.post.side_effect = [
        {"request_id": "request", "code": "ABC123"},
        {"status": decision},
        {},
    ]
    monkeypatch.setattr(login, "AsyncBaseClient", lambda *_: client)
    path = tmp_path / "credential.json"
    monkeypatch.setattr(login, "credential_path", lambda *_: path)
    output = []
    assert await login.terminal_login(None, "Editor", report=output.append) == expected
    assert path.exists() == (expected == 0)
    assert "ABC123" in output[0]
    assert client.post.call_count == (2 if expected == 0 else 3)
    client.aclose.assert_awaited_once()
