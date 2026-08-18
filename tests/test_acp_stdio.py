"""Focused tests for the local stdio ACP transport."""

import json
import sys

import pytest

from suzent.acp.client import ACPClient
from suzent.acp.registry import ACPAgentRegistry


MOCK_AGENT = r"""
import json, sys
session = "mock-session"
for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{"protocolVersion":1}}), flush=True)
    elif method == "session/new":
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{"sessionId":session}}), flush=True)
    elif method == "session/load":
        session = msg["params"]["sessionId"]
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{"sessionId":session}}), flush=True)
    elif method == "session/prompt":
        print(json.dumps({"jsonrpc":"2.0","id":77,"method":"session/request_permission","params":{"sessionId":session,"options":[]}}), flush=True)
        denied = json.loads(sys.stdin.readline())
        assert denied["result"]["outcome"]["outcome"] == "cancelled"
        print(json.dumps({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":session,"update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"hello"}}}}), flush=True)
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{"stopReason":"end_turn"}}), flush=True)
"""


@pytest.mark.asyncio
async def test_stdio_client_session_prompt_and_permission_denial(tmp_path):
    script = tmp_path / "mock_acp.py"
    script.write_text(MOCK_AGENT, encoding="utf-8")
    updates = []

    async def on_notification(method, params):
        updates.append((method, params))

    client = ACPClient(
        [sys.executable, "-u", str(script)], notification_handler=on_notification
    )
    await client.start()
    created = await client.new_session(str(tmp_path))
    assert created["sessionId"] == "mock-session"
    result = await client.prompt("mock-session", "hi")
    assert result["stopReason"] == "end_turn"
    assert updates[0][0] == "session/update"
    assert updates[0][1]["update"]["content"]["text"] == "hello"
    await client.close()


@pytest.mark.asyncio
async def test_stdio_client_loads_session(tmp_path):
    script = tmp_path / "mock_acp.py"
    script.write_text(MOCK_AGENT, encoding="utf-8")
    client = ACPClient([sys.executable, "-u", str(script)])
    await client.start()
    loaded = await client.load_session("existing", str(tmp_path))
    assert loaded["sessionId"] == "existing"
    await client.close()
    assert client.process is None


def test_registry_merges_builtins_and_user_agents(tmp_path, monkeypatch):
    config = tmp_path / "acp_agents.json"
    config.write_text(
        json.dumps(
            {"agents": [{"id": "mock", "name": "Mock", "command": [sys.executable]}]}
        ),
        encoding="utf-8",
    )
    agents = {agent.id: agent for agent in ACPAgentRegistry(config).list_agents()}
    assert {"claude-code", "codex-acp", "mock"} <= set(agents)
    assert agents["mock"].available is True
    assert all(
        "agent-sdk" not in " ".join(agent.command).lower() for agent in agents.values()
    )
