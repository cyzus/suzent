"""Regression tests for the ACP handshake, resume fallback, and probe route."""

import json
import sys

import pytest

from suzent.acp.manager import ACPManager
from suzent.acp.registry import ACPAgentRegistry

# Behaves like a real ACP agent: refuses session methods before `initialize`,
# and advertises whether it can load a previous session.
STRICT_AGENT = r"""
import json, sys
LOAD = {load}
initialized = False
for line in sys.stdin:
    msg = json.loads(line)
    m = msg.get("method")
    if m == "initialize":
        initialized = True
        print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"result":{{
            "protocolVersion":1,
            "agentCapabilities":{{"loadSession":LOAD}},
            "agentInfo":{{"name":"strict-mock","version":"9"}}}}}}), flush=True)
    elif m in ("session/new", "session/load"):
        if not initialized:
            print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"error":{{
                "code":-32002,"message":"initialize must be called first"}}}}), flush=True)
        elif m == "session/load" and not LOAD:
            print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"error":{{
                "code":-32601,"message":"session/load unsupported"}}}}), flush=True)
        else:
            sid = msg["params"].get("sessionId", "fresh-session")
            print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"result":{{"sessionId":sid}}}}), flush=True)
"""


def _manager(tmp_path, load_session: bool) -> ACPManager:
    script = tmp_path / f"strict_{load_session}.py"
    script.write_text(STRICT_AGENT.format(load="True" if load_session else "False"))
    config = tmp_path / "acp_agents.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "strict",
                        "name": "Strict",
                        "command": [sys.executable, "-u", str(script)],
                    }
                ]
            }
        )
    )
    return ACPManager(ACPAgentRegistry(config))


@pytest.mark.asyncio
async def test_connect_performs_initialize_before_session_new(tmp_path):
    """A spec-compliant agent rejects session/new unless `initialize` ran first."""
    manager = _manager(tmp_path, load_session=True)
    try:
        managed = await manager.create("chat-1", "strict", str(tmp_path))
        assert managed.session_id == "fresh-session"
        assert managed.protocol_version == 1
        assert managed.capabilities == {"loadSession": True}
        assert managed.agent_info["name"] == "strict-mock"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_resume_loads_session_when_agent_supports_it(tmp_path):
    manager = _manager(tmp_path, load_session=True)
    try:
        managed = await manager.resume(
            "chat-1", "strict", "prior-session", str(tmp_path)
        )
        assert managed.session_id == "prior-session"
        assert managed.resumed is True
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_resume_falls_back_to_new_session_without_load_capability(tmp_path):
    """Agents that can't load sessions must still get a usable session."""
    manager = _manager(tmp_path, load_session=False)
    try:
        managed = await manager.resume(
            "chat-1", "strict", "prior-session", str(tmp_path)
        )
        assert managed.session_id == "fresh-session"
        assert managed.resumed is False
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_probe_returns_handshake_data_and_leaves_no_process(
    tmp_path, monkeypatch
):
    import suzent.acp.manager as manager_module
    from suzent.routes.acp_routes import probe_acp_agent

    manager = _manager(tmp_path, load_session=True)
    monkeypatch.setattr(manager_module, "_manager", manager)

    class _Request:
        path_params = {"agent_id": "strict"}

    try:
        response = await probe_acp_agent(_Request())
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["protocolVersion"] == 1
        assert body["capabilities"] == {"loadSession": True}
        assert body["agentInfo"]["name"] == "strict-mock"
        # The probe subprocess must be torn down, not left running.
        assert manager.list_active() == []
    finally:
        await manager.shutdown()


def _events(chunks):
    out = []
    for chunk in chunks:
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
            out.append(json.loads(chunk[6:].strip()))
    return out


async def _collect_turn(prompt_impl):
    """Drive stream_acp_turn against a stubbed manager/database."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "s"}
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "s", "/tmp"
        managed.client.prompt = prompt_impl
        managed.updates = asyncio.Queue()

        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        return _events([chunk async for chunk in stream_acp_turn("chat-1", "hi")])


@pytest.mark.asyncio
async def test_turn_closes_assistant_message_when_agent_errors():
    """A mid-turn failure must still emit TEXT_MESSAGE_END, or the UI streams forever."""

    async def boom(session_id, message):
        raise RuntimeError("agent crashed")

    events = await _collect_turn(boom)
    types = [event["type"] for event in events]
    assert "TEXT_MESSAGE_START" in types
    assert "TEXT_MESSAGE_END" in types
    assert types.index("TEXT_MESSAGE_END") < types.index("RUN_ERROR")
    assert "agent crashed" in events[-1]["message"]


@pytest.mark.asyncio
async def test_turn_closes_assistant_message_when_output_is_empty():
    async def silent(session_id, message):
        return {"text": ""}

    events = await _collect_turn(silent)
    types = [event["type"] for event in events]
    assert types.index("TEXT_MESSAGE_END") < types.index("RUN_ERROR")


def test_user_override_keeps_builtin_install_metadata(tmp_path):
    """Repointing a built-in's command must not strip its setup commands."""
    config = tmp_path / "acp_agents.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {"id": "claude-code", "command": ["/opt/my/acp-adapter"]},
                    {"id": "custom", "command": ["whatever"]},
                ]
            }
        )
    )
    agents = {a.id: a for a in ACPAgentRegistry(config).list_agents()}

    overridden = agents["claude-code"]
    assert overridden.command == ["/opt/my/acp-adapter"]
    assert overridden.install_command is not None
    assert overridden.login_command == ["claude", "auth", "login"]
    assert overridden.name == "Claude Code"
    assert overridden.builtin is True

    # A genuinely new agent has no metadata to inherit.
    assert agents["custom"].install_command is None
    assert agents["custom"].builtin is False


@pytest.mark.asyncio
async def test_turn_announces_when_resume_lost_the_session():
    """A silent fresh session looks like amnesia; the stream must say so."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "old-1"}
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "new-2", "/tmp"
        managed.resumed = False
        managed.updates = asyncio.Queue()

        async def prompt(session_id, message):
            return {"text": "hi"}

        managed.client.prompt = prompt
        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        events = _events([c async for c in stream_acp_turn("chat-1", "hi")])

    resets = [e for e in events if e.get("name") == "acp.session_reset"]
    assert len(resets) == 1
    assert resets[0]["value"]["requestedSessionId"] == "old-1"
    assert resets[0]["value"]["sessionId"] == "new-2"
