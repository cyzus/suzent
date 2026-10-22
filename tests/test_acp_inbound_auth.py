"""ACP auth capability negotiation, session ownership and live revocation."""

import asyncio
import json
import os
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from suzent.acp.server import ACPAgentServer, AUTH_REQUIRED, SESSION_MARKER
from test_acp_server import FakeBackend, Wire, request


def test_real_cli_registry_handshake_without_running_backend(tmp_path):
    # Avoid importing real legacy user data into this isolated subprocess.
    (tmp_path / ".pytest").touch()
    payload = request(
        1,
        "initialize",
        {
            "protocolVersion": 1,
            "clientInfo": {"name": "ACP Registry Validator", "version": "1.0.0"},
            "clientCapabilities": {
                "terminal": True,
                "_meta": {"terminal-auth": True, "terminal_output": True},
            },
        },
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "suzent.cli",
            "acp",
            "--server-url",
            "http://127.0.0.1:1",
        ],
        input=json.dumps(payload) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={**os.environ, "SUZENT_DATA_DIR": str(tmp_path), "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["result"]["authMethods"][0]["id"] == "suzent-pair"
    assert response["id"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [True, False])
async def test_auth_methods_require_terminal_capability(terminal):
    wire = Wire()
    server = ACPAgentServer(FakeBackend([]), wire, require_auth=True)
    await server.dispatch(
        request(
            1,
            "initialize",
            {
                "clientInfo": {"name": "editor"},
                "clientCapabilities": {"auth": {"terminal": terminal}},
            },
        )
    )
    methods = wire.result(1)["authMethods"]
    assert any(method.get("type") == "terminal" for method in methods) is terminal
    assert methods[-1]["id"] == "suzent-pair"
    if terminal:
        assert methods[0]["type"] == "terminal"
        assert methods[0]["args"] == ["--login", "--client-name", "editor"]
    await server.dispatch(request(2, "authenticate", {"methodId": "suzent-terminal"}))
    assert wire.error(2)


@pytest.mark.asyncio
async def test_agent_auth_waits_for_pairing_then_reloads_credential(monkeypatch):
    from suzent.acp import login

    backend = FakeBackend([])
    backend.base_url = "http://localhost:25314"
    backend.verify_token = AsyncMock(return_value="grant")
    secret = ""

    async def approve(*args, **kwargs):
        nonlocal secret
        secret = "saved-credential"
        return 0

    monkeypatch.setattr(login, "terminal_login", approve)
    wire = Wire()
    server = ACPAgentServer(
        backend, wire, require_auth=True, token_loader=lambda _: secret
    )
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "authenticate", {"methodId": "suzent-pair"}))
    assert wire.result(2) == {}
    backend.verify_token.assert_awaited_with("saved-credential")


@pytest.mark.asyncio
async def test_unauthenticated_session_cannot_reach_backend(tmp_path):
    backend = FakeBackend([])
    wire = Wire()
    server = ACPAgentServer(backend, wire, require_auth=True)
    await server.dispatch(request(1, "session/new", {"cwd": str(tmp_path)}))
    assert wire.error(1)["code"] == AUTH_REQUIRED
    assert not backend.created


@pytest.mark.asyncio
async def test_authorization_owns_history_and_revocation_blocks_prompts(tmp_path):
    backend = FakeBackend([])
    backend.verify_token = AsyncMock(return_value="grant-a")
    wire = Wire()
    server = ACPAgentServer(
        backend, wire, require_auth=True, token_loader=lambda _: "secret"
    )
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))
    assert backend.created[0][1][SESSION_MARKER]["grant_id"] == "grant-a"
    backend.chats["chat-1"]["messages"] = [{"role": "assistant", "content": "private"}]
    await server.dispatch(request(3, "session/load", {"sessionId": "chat-1"}))
    assert wire.error(3) is None
    wire.sent.clear()
    backend.verify_token.return_value = "grant-b"
    await server.dispatch(request(4, "session/load", {"sessionId": "chat-1"}))
    assert wire.error(4)["code"] == AUTH_REQUIRED
    assert not wire.updates()
    backend.verify_token.return_value = None
    await server.dispatch(
        request(
            5,
            "session/prompt",
            {
                "sessionId": "chat-1",
                "prompt": [{"type": "text", "text": "hello"}],
            },
        )
    )
    await server.drain()
    assert wire.error(5)["code"] == AUTH_REQUIRED
    assert not backend.payloads


@pytest.mark.asyncio
async def test_revocation_stops_a_silent_running_turn(tmp_path):
    started = asyncio.Event()
    finished = asyncio.Event()

    class SilentBackend(FakeBackend):
        async def stream_turn(self, payload):
            started.set()
            try:
                await asyncio.Event().wait()
                yield b""
            finally:
                finished.set()

    backend = SilentBackend([])
    backend.verify_token = AsyncMock(return_value="grant")
    wire = Wire()
    server = ACPAgentServer(
        backend, wire, require_auth=True, token_loader=lambda _: "secret"
    )
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))
    await server.dispatch(
        request(
            3,
            "session/prompt",
            {
                "sessionId": "chat-1",
                "prompt": [{"type": "text", "text": "hello"}],
            },
        )
    )
    await asyncio.wait_for(started.wait(), 2)
    backend.verify_token.return_value = None
    await asyncio.wait_for(server.drain(), 3)
    assert wire.error(3)["code"] == AUTH_REQUIRED
    assert backend.stopped == ["chat-1"]
    assert finished.is_set()
