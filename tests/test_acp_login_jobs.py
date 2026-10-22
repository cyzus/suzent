"""Outbound login routing, cancellation and local operator boundaries."""

import asyncio
from dataclasses import replace
import json
import os
import sys
from unittest.mock import AsyncMock

import httpx
import pytest
import psutil
from starlette.applications import Starlette

from suzent.acp import authentication, terminal_login
from suzent.acp.manager import ACPManager
from suzent.acp.registry import ACPAgentRegistry
from suzent.routes import acp_auth_routes

pytest_plugins = ["test_acp_authentication"]


async def test_protocol_login_verifies_and_preserves_live_connection(
    auth_manager, tmp_path
):
    state = auth_manager.logins.start("test-auth", str(tmp_path))
    assert state.status == "starting"
    assert (
        auth_manager.logins.start("test-auth", str(tmp_path)).attempt == state.attempt
    )
    await auth_manager.logins.tasks["test-auth"]
    assert auth_manager.logins.state("test-auth").status == "ready"
    assert auth_manager.logins.state("test-auth").result["status"] == "ready"
    assert "test-auth" in auth_manager._authenticated
    await auth_manager.shutdown()


@pytest.fixture
def terminal_manager(tmp_path):
    script = tmp_path / "terminal-agent.py"
    script.write_text(
        """
import json, sys
from pathlib import Path
for line in sys.stdin:
    req = json.loads(line)
    if req["method"] == "initialize":
        assert req["params"]["clientCapabilities"]["auth"]["terminal"] is True
        result = {"protocolVersion": 1, "authMethods": [{"id": "terminal", "type": "terminal", "args": ["--login"], "env": {"OVERRIDE": "method"}}]}
    elif req["method"] == "session/new":
        if not Path(sys.argv[1]).exists():
            print(json.dumps({"id": req["id"], "error": {"code": -32000, "message": "login required"}}), flush=True)
            continue
        result = {"sessionId": "ok"}
    else:
        raise AssertionError("terminal method must not call authenticate")
    print(json.dumps({"id": req["id"], "result": result}), flush=True)
""",
        encoding="utf-8",
    )
    config = tmp_path / "registry.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "test-terminal",
                        "name": "Terminal",
                        "command": [
                            sys.executable,
                            str(script),
                            str(tmp_path / "signed-in"),
                        ],
                        "env": {"OVERRIDE": "base", "KEEP": "base"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return ACPManager(ACPAgentRegistry(config))


async def test_terminal_login_uses_base_command_and_overrides(
    terminal_manager, tmp_path, monkeypatch
):
    monkeypatch.setattr(authentication, "terminal_available", lambda: True)
    monkeypatch.setattr(terminal_login, "terminal_available", lambda: True)

    async def approve(command, cwd, env):
        assert command == [
            *terminal_manager.registry.get("test-terminal").command,
            "--login",
        ]
        assert cwd == str(tmp_path)
        assert env["OVERRIDE"] == "method"
        assert env["KEEP"] == "base"
        (tmp_path / "signed-in").touch()

    monkeypatch.setattr(authentication, "run_terminal_login", approve)
    terminal_manager.logins.start("test-terminal", str(tmp_path))
    await terminal_manager.logins.tasks["test-terminal"]
    assert terminal_manager.logins.state("test-terminal").status == "ready"
    await terminal_manager.shutdown()


async def test_terminal_success_without_credentials_is_not_login_success(
    terminal_manager, tmp_path, monkeypatch
):
    monkeypatch.setattr(authentication, "terminal_available", lambda: True)
    monkeypatch.setattr(terminal_login, "terminal_available", lambda: True)
    monkeypatch.setattr(authentication, "run_terminal_login", AsyncMock())
    terminal_manager.logins.start("test-terminal", str(tmp_path))
    await terminal_manager.logins.tasks["test-terminal"]
    assert terminal_manager.logins.state("test-terminal").error == "verification_failed"
    await terminal_manager.shutdown()


async def test_cancel_waiting_terminal_and_shutdown(
    terminal_manager, tmp_path, monkeypatch
):
    monkeypatch.setattr(authentication, "terminal_available", lambda: True)
    entered = asyncio.Event()
    closed = asyncio.Event()

    async def waiting(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(authentication, "run_terminal_login", waiting)
    terminal_manager.logins.start("test-terminal", str(tmp_path))
    await asyncio.wait_for(entered.wait(), 5)
    await terminal_manager.shutdown()
    assert closed.is_set()
    assert terminal_manager.logins.state("test-terminal").status == "cancelled"


async def test_native_worker_round_trip_without_vendor_login(tmp_path, monkeypatch):
    # Run the exact terminal worker without opening a user window in the test suite.
    monkeypatch.setattr(terminal_login, "terminal_command", lambda worker: worker)
    monkeypatch.setattr(
        terminal_login.subprocess, "CREATE_NEW_CONSOLE", 0, raising=False
    )
    script = tmp_path / "login.py"
    script.write_text(
        "from pathlib import Path\nPath('done').write_text('ok')", encoding="utf-8"
    )
    await terminal_login.run_terminal_login(
        [sys.executable, str(script)], str(tmp_path), dict(os.environ), timeout=10
    )
    assert (tmp_path / "done").read_text() == "ok"


@pytest.mark.parametrize(
    "remote,origin",
    [
        ("192.0.2.1", None),
        ("127.0.0.1", "https://attacker.example"),
        ("127.0.0.1", "null"),
    ],
)
async def test_login_controls_are_local_only(remote, origin):
    app = Starlette(routes=acp_auth_routes.acp_auth_routes)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(remote, 42)),
        base_url="http://localhost",
    ) as client:
        headers = {"Origin": origin} if origin else {}
        for path, method in [
            ("/acp/logins", "GET"),
            ("/acp/agents/codex/login", "POST"),
            ("/acp/agents/codex/login", "DELETE"),
        ]:
            assert (
                await client.request(method, path, headers=headers)
            ).status_code == 403


async def test_login_endpoint_never_accepts_arbitrary_commands(
    auth_manager, monkeypatch
):
    monkeypatch.setattr(acp_auth_routes, "get_acp_manager", lambda: auth_manager)
    app = Starlette(routes=acp_auth_routes.acp_auth_routes)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 42)),
        base_url="http://localhost",
    ) as client:
        result = await client.post(
            "/acp/agents/test-auth/login", json={"command": ["anything"]}
        )
        assert result.status_code == 400
        assert not auth_manager.logins.tasks


@pytest.mark.parametrize("stop", ["cancel", "timeout"])
async def test_native_worker_cleans_up_running_child(tmp_path, monkeypatch, stop):
    monkeypatch.setattr(terminal_login, "terminal_command", lambda worker: worker)
    monkeypatch.setattr(
        terminal_login.subprocess, "CREATE_NEW_CONSOLE", 0, raising=False
    )
    script = tmp_path / "waiting.py"
    script.write_text(
        "import os, time\nfrom pathlib import Path\nPath('pid').write_text(str(os.getpid()))\ntime.sleep(60)",
        encoding="utf-8",
    )
    task = asyncio.create_task(
        terminal_login.run_terminal_login(
            [sys.executable, str(script)],
            str(tmp_path),
            dict(os.environ),
            timeout=3 if stop == "timeout" else 15,
        )
    )
    async with asyncio.timeout(5):
        while not (tmp_path / "pid").exists():
            await asyncio.sleep(0.05)
    pid = int((tmp_path / "pid").read_text())
    if stop == "cancel":
        task.cancel()
    with pytest.raises(asyncio.CancelledError if stop == "cancel" else TimeoutError):
        await task
    async with asyncio.timeout(3):
        while psutil.pid_exists(pid):
            await asyncio.sleep(0.05)


async def test_native_worker_failed_exit_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr(terminal_login, "terminal_command", lambda worker: worker)
    monkeypatch.setattr(
        terminal_login.subprocess, "CREATE_NEW_CONSOLE", 0, raising=False
    )
    with pytest.raises(ValueError, match="failed"):
        await terminal_login.run_terminal_login(
            [sys.executable, "-c", "raise SystemExit(2)"],
            str(tmp_path),
            dict(os.environ),
            timeout=10,
        )


@pytest.mark.parametrize("exit_code,expected", [(0, True), (1, False), (2, None)])
async def test_claude_status_checks_exit_code_without_api_credentials(
    monkeypatch, tmp_path, exit_code, expected
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    monkeypatch.setattr(
        authentication.shutil, "which", lambda *args, **kwargs: "claude"
    )
    process = AsyncMock()
    process.wait.return_value = exit_code
    process.returncode = exit_code
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(authentication.asyncio, "create_subprocess_exec", spawn)
    if expected is None:
        with pytest.raises(ValueError):
            await authentication.claude_authenticated(
                str(tmp_path), {"ANTHROPIC_AUTH_TOKEN": "must-not-leak"}
            )
    else:
        assert (
            await authentication.claude_authenticated(
                str(tmp_path), {"ANTHROPIC_AUTH_TOKEN": "must-not-leak"}
            )
            is expected
        )
    assert spawn.call_args.args == ("claude", "auth", "status")
    assert "ANTHROPIC_API_KEY" not in spawn.call_args.kwargs["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in spawn.call_args.kwargs["env"]


async def test_cli_fallback_reconnects_and_verifies(
    auth_manager, tmp_path, monkeypatch
):
    agent = replace(
        auth_manager.registry.get("test-auth"),
        login_command=[sys.executable, "login.py"],
    )
    monkeypatch.setattr(auth_manager.registry, "get", lambda _: agent)
    monkeypatch.setattr(authentication, "terminal_available", lambda: True)
    client = AsyncMock()
    client.initialize.return_value = {"authMethods": []}
    monkeypatch.setattr(authentication, "ACPClient", lambda *args, **kwargs: client)
    terminal = AsyncMock()
    monkeypatch.setattr(authentication, "run_terminal_login", terminal)
    monkeypatch.setattr(
        auth_manager,
        "probe",
        AsyncMock(return_value={"status": "ready", "authMethods": []}),
    )
    auth_manager.logins.start("test-auth", str(tmp_path))
    await auth_manager.logins.tasks["test-auth"]
    assert terminal.call_args.args[0] == agent.login_command
    client.authenticate.assert_not_called()
    client.close.assert_awaited_once()
    auth_manager.probe.assert_awaited_once()
    assert auth_manager.logins.state("test-auth").status == "ready"


async def test_login_endpoint_lifecycle(auth_manager, tmp_path, monkeypatch):
    agent = replace(auth_manager.registry.get("test-auth"), cwd=str(tmp_path))
    monkeypatch.setattr(auth_manager.registry, "get", lambda _: agent)
    monkeypatch.setattr(acp_auth_routes, "get_acp_manager", lambda: auth_manager)
    app = Starlette(routes=acp_auth_routes.acp_auth_routes)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 42)),
        base_url="http://localhost",
    ) as client:
        result = await client.post("/acp/agents/test-auth/login", json={})
        assert result.status_code == 202
        await auth_manager.logins.tasks["test-auth"]
        result = await client.get("/acp/logins")
        assert result.headers["cache-control"] == "no-store"
        assert result.json()["test-auth"]["status"] == "ready"
        assert (await client.delete("/acp/agents/test-auth/login")).status_code == 200
    await auth_manager.shutdown()
