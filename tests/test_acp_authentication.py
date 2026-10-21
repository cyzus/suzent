"""Protocol authentication and transport regressions using a local ACP process."""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from suzent.acp.client import ACPClient, ACPError
from suzent.acp.manager import ACPManager
from suzent.acp.registry import ACPAgentRegistry


AGENT = """
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
signed_in = (root / "signed-in").exists()
for line in sys.stdin:
    req = json.loads(line)
    method = req["method"]
    with (root / "calls").open("a") as log:
        log.write(method + "\\n")
    result = {}
    error = None
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {"loadSession": True},
                  "authMethods": [{"id": "browser", "name": "Browser"},
                                  {"id": "terminal", "type": "terminal", "name": "CLI"}]}
    elif method == "authenticate":
        assert req["params"]["methodId"] == "browser"
        (root / "signed-in").touch()
        signed_in = True
    elif method in ("session/new", "session/load"):
        if not signed_in:
            error = {"code": -32000, "message": "Sign in", "data": {"reason": "expired"}}
        else:
            result = {"sessionId": req["params"].get("sessionId", "fresh")}
    elif method == "session/prompt":
        count = 4100 if req["params"]["prompt"][0]["text"] == "overflow" else 1
        for i in range(count):
            print(json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": {
                "sessionId": "fresh", "update": {"sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "x" * (100000 if count == 1 else 1)}}}}), flush=True)
        result = {"stopReason": "end_turn"}
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"],
                     **({"error": error} if error else {"result": result})}), flush=True)
"""


@pytest.fixture
def auth_manager(tmp_path: Path) -> ACPManager:
    script = tmp_path / "agent.py"
    script.write_text(AGENT, encoding="utf-8")
    config = tmp_path / "registry.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "test-auth",
                        "name": "Test",
                        "command": [sys.executable, "-u", str(script), str(tmp_path)],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return ACPManager(ACPAgentRegistry(config))


async def test_probe_login_and_resume(auth_manager: ACPManager, tmp_path: Path) -> None:
    result = await auth_manager.probe("test-auth", str(tmp_path))
    assert result["status"] == "auth_required"
    assert result["authMethods"][0]["id"] == "browser"
    assert auth_manager.list_active() == []
    result = await auth_manager.probe("test-auth", str(tmp_path), "browser")
    assert result["status"] == "ready"
    (tmp_path / "signed-in").unlink()
    assert (await auth_manager.probe("test-auth", str(tmp_path)))["status"] == "ready"
    project = tmp_path / "project"
    project.mkdir()
    try:
        session = await auth_manager.resume(
            "chat", "test-auth", "original", str(project)
        )
        assert session.session_id == "original"
    finally:
        await auth_manager.shutdown()


@pytest.mark.parametrize("method", ["unknown", "terminal"])
async def test_rejects_unadvertised_or_terminal_login(
    auth_manager: ACPManager, tmp_path: Path, method: str
) -> None:
    with pytest.raises(ValueError):
        await auth_manager.probe("test-auth", str(tmp_path), method)
    assert "authenticate" not in (tmp_path / "calls").read_text()


async def test_auth_error_preserves_resume_target(
    auth_manager: ACPManager, tmp_path: Path
) -> None:
    with pytest.raises(ACPError) as raised:
        await auth_manager.resume("chat", "test-auth", "original", str(tmp_path))
    assert raised.value.auth_required
    assert raised.value.message == "Sign in"
    assert raised.value.data == {"reason": "expired"}
    assert "session/new" not in (tmp_path / "calls").read_text()


async def test_large_stream_frame(auth_manager: ACPManager, tmp_path: Path) -> None:
    (tmp_path / "signed-in").touch()
    try:
        session = await auth_manager.create("chat", "test-auth", str(tmp_path))
        await session.client.prompt(session.session_id, "large")
        update = session.updates.get_nowait()
        assert len(update["update"]["content"]["text"]) == 100000
    finally:
        await auth_manager.shutdown()


async def test_overflow_fails_without_blocking_rpc(
    auth_manager: ACPManager, tmp_path: Path
) -> None:
    import asyncio

    (tmp_path / "signed-in").touch()
    try:
        session = await auth_manager.create("chat", "test-auth", str(tmp_path))
        with pytest.raises(ACPError, match="overflow"):
            await asyncio.wait_for(
                session.client.prompt(session.session_id, "overflow"), 5
            )
        assert session.updates.qsize() == 4096
        reconnected = await auth_manager.resume(
            "chat", "test-auth", session.session_id, str(tmp_path)
        )
        assert reconnected.client is not session.client
        assert reconnected.resumed
    finally:
        await auth_manager.shutdown()


async def test_failed_write_does_not_leak_pending_request() -> None:
    from unittest.mock import AsyncMock, MagicMock

    client = ACPClient([])
    client.process = MagicMock(returncode=None)
    client._send = AsyncMock(side_effect=BrokenPipeError)
    with pytest.raises(BrokenPipeError):
        await client.request("initialize")
    assert not client._pending


async def test_auth_route_validates_input_and_closes_probe(
    auth_manager: ACPManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from suzent.routes.acp_routes import authenticate_acp_agent

    monkeypatch.setattr(
        "suzent.routes.acp_routes.get_acp_manager", lambda: auth_manager
    )
    request = SimpleNamespace(
        path_params={"agent_id": "test-auth"}, json=AsyncMock(return_value={})
    )
    assert (await authenticate_acp_agent(request)).status_code == 400
    request.json.return_value = {"method_id": "not-advertised"}
    assert (await authenticate_acp_agent(request)).status_code == 400
    assert not auth_manager._authenticated


async def test_stream_drains_final_updates_in_order() -> None:
    import asyncio
    from types import SimpleNamespace
    from suzent.acp.runtime import _stream_prompt

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def prompt(
        session_id: str, message: str, on_sent: Callable[[], None]
    ) -> dict[str, str]:
        on_sent()
        for text in ["first", "last"]:
            queue.put_nowait(
                {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": text},
                    }
                }
            )
        return {"stopReason": "end_turn"}

    managed = SimpleNamespace(
        session_id="session", updates=queue, client=SimpleNamespace(prompt=prompt)
    )
    state = {"parts": [], "stop_reason": "", "error": ""}
    frames = [frame async for frame in _stream_prompt(managed, "hi", "message", state)]
    assert len(frames) == 2
    assert state["parts"] == ["first", "last"]
    assert state["stop_reason"] == "end_turn"
