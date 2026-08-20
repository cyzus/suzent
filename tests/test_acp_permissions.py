"""Tests for relaying ACP permission requests to a policy, agent, or human."""

import asyncio
import json
import sys

import pytest

from suzent.acp.client import ACPClient
from suzent.acp.manager import ACPManager
from suzent.acp.permissions import (
    PERMISSION_QUEUE_KEY,
    ACPPermissionBroker,
    select_option,
)
from suzent.acp.registry import ACPAgentRegistry

OPTIONS = [
    {"optionId": "yes", "name": "Allow", "kind": "allow_once"},
    {"optionId": "always", "name": "Always", "kind": "allow_always"},
    {"optionId": "no", "name": "Reject", "kind": "reject_once"},
]

# Asks permission mid-turn, streams an update, then finishes. Mirrors how a real
# agent interleaves reverse requests with session/update notifications.
PERMISSION_AGENT = r"""
import json, sys, threading
def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    msg = json.loads(line)
    m = msg.get("method")
    if m == "initialize":
        send({"jsonrpc":"2.0","id":msg["id"],"result":{"protocolVersion":1,
             "agentCapabilities":{"loadSession":True},"agentInfo":{"name":"perm"}}})
    elif m == "session/new":
        send({"jsonrpc":"2.0","id":msg["id"],"result":{"sessionId":"s1"}})
    elif m == "session/prompt":
        send({"jsonrpc":"2.0","id":9001,"method":"session/request_permission",
              "params":{"sessionId":"s1",
                        "toolCall":{"toolCallId":"t1","title":"Write file","kind":"edit"},
                        "options":OPTIONS_JSON}})
        # While waiting for the answer, keep emitting updates. If the client
        # blocked its read loop on the decision this would never be observed.
        send({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"s1",
              "update":{"sessionUpdate":"agent_message_chunk",
                        "content":{"type":"text","text":"working"}}}})
        reply = json.loads(sys.stdin.readline())
        outcome = reply["result"]["outcome"]
        send({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"s1",
              "update":{"sessionUpdate":"agent_message_chunk",
                        "content":{"type":"text","text":"|" + json.dumps(outcome)}}}})
        send({"jsonrpc":"2.0","id":msg["id"],"result":{"stopReason":"end_turn"}})
""".replace("OPTIONS_JSON", json.dumps(OPTIONS))


def _write_agent(tmp_path):
    script = tmp_path / "perm_agent.py"
    script.write_text(PERMISSION_AGENT)
    config = tmp_path / "acp_agents.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "perm",
                        "name": "Perm",
                        "command": [sys.executable, "-u", str(script)],
                    }
                ]
            }
        )
    )
    return config


def test_select_option_prefers_earlier_kinds():
    assert select_option(OPTIONS, ("allow_once", "allow_always")) == "yes"
    assert select_option(OPTIONS, ("allow_always",)) == "always"
    assert select_option(OPTIONS, ("reject_always",)) is None


@pytest.mark.asyncio
async def test_auto_mode_approves_without_prompting():
    broker = ACPPermissionBroker()
    relayed = []
    outcome = await broker.request(
        "chat-1",
        {"sessionId": "s1", "options": OPTIONS},
        permission_mode="auto",
        on_relay=lambda event: relayed.append(event),
    )
    assert outcome == {"outcome": {"outcome": "selected", "optionId": "yes"}}
    assert relayed == [], "auto mode must not bother a human"
    assert broker.list_pending() == []


@pytest.mark.asyncio
async def test_relayed_request_waits_for_a_decision():
    broker = ACPPermissionBroker()
    relayed = asyncio.Event()
    events = []

    def on_relay(event):
        events.append(event)
        relayed.set()

    task = asyncio.create_task(
        broker.request(
            "chat-1", {"sessionId": "s1", "options": OPTIONS}, on_relay=on_relay
        )
    )
    await asyncio.wait_for(relayed.wait(), timeout=2)
    assert not task.done(), "must block until something decides"
    assert broker.list_pending("chat-1")

    request_id = events[0]["requestId"]
    assert events[0]["toolCall"] == {}
    assert broker.resolve(request_id, approved=True) is True
    assert await asyncio.wait_for(task, timeout=2) == {
        "outcome": {"outcome": "selected", "optionId": "yes"}
    }
    assert broker.list_pending() == []


@pytest.mark.asyncio
async def test_denial_and_explicit_option_are_honoured():
    broker = ACPPermissionBroker()
    started = asyncio.Event()
    ids = []

    def on_relay(event):
        ids.append(event["requestId"])
        started.set()

    task = asyncio.create_task(
        broker.request("c", {"options": OPTIONS}, on_relay=on_relay)
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    broker.resolve(ids[0], approved=False)
    assert await asyncio.wait_for(task, timeout=2) == {
        "outcome": {"outcome": "cancelled"}
    }

    started.clear()
    ids.clear()
    task = asyncio.create_task(
        broker.request("c", {"options": OPTIONS}, on_relay=on_relay)
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    broker.resolve(ids[0], approved=True, option_id="always")
    assert await asyncio.wait_for(task, timeout=2) == {
        "outcome": {"outcome": "selected", "optionId": "always"}
    }


@pytest.mark.asyncio
async def test_timeout_fails_closed():
    broker = ACPPermissionBroker()
    outcome = await broker.request(
        "c", {"options": OPTIONS}, on_relay=lambda e: None, timeout=0.05
    )
    assert outcome == {"outcome": {"outcome": "cancelled"}}
    assert broker.list_pending() == []


@pytest.mark.asyncio
async def test_cancel_chat_releases_waiters():
    broker = ACPPermissionBroker()
    started = asyncio.Event()
    task = asyncio.create_task(
        broker.request("c", {"options": OPTIONS}, on_relay=lambda e: started.set())
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    assert broker.cancel_chat("c") == 1
    assert await asyncio.wait_for(task, timeout=2) == {
        "outcome": {"outcome": "cancelled"}
    }


@pytest.mark.asyncio
async def test_client_without_handler_still_fails_closed(tmp_path):
    """Default behaviour must stay deny, not accidental approval."""
    script = tmp_path / "a.py"
    script.write_text(PERMISSION_AGENT)
    client = ACPClient([sys.executable, "-u", str(script)])
    await client.start()
    try:
        await client.initialize()
        await client.new_session(str(tmp_path))
        result = await client.prompt("s1", "go")
        assert result["stopReason"] == "end_turn"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_permission_does_not_stall_the_update_stream(tmp_path):
    """Updates must keep flowing while a permission request awaits a decision.

    Answering inside the read loop would deadlock: the decision arrives over the
    stream we would have stopped reading.
    """
    manager = ACPManager(ACPAgentRegistry(_write_agent(tmp_path)))
    from suzent.acp.permissions import get_permission_broker

    broker = get_permission_broker()
    try:
        managed = await manager.create("chat-x", "perm", str(tmp_path))
        prompt = asyncio.create_task(managed.client.prompt(managed.session_id, "go"))

        # The relay event and the mid-wait "working" chunk must both arrive
        # before we answer.
        relayed = None
        saw_chunk = False
        for _ in range(80):
            item = await asyncio.wait_for(managed.updates.get(), timeout=5)
            if PERMISSION_QUEUE_KEY in item:
                relayed = item[PERMISSION_QUEUE_KEY]
            elif "working" in json.dumps(item):
                saw_chunk = True
            if relayed and saw_chunk:
                break
        assert relayed is not None, "permission request was never relayed"
        assert saw_chunk, "read loop stalled while awaiting the decision"
        assert relayed["toolCall"]["title"] == "Write file"

        assert broker.resolve(relayed["requestId"], approved=True) is True
        assert (await asyncio.wait_for(prompt, timeout=10))["stopReason"] == "end_turn"

        # The agent echoes back what it received, proving the outcome reached it.
        tail = await asyncio.wait_for(managed.updates.get(), timeout=5)
        echoed = json.loads(tail["update"]["content"]["text"].lstrip("|"))
        assert echoed == {"outcome": "selected", "optionId": "yes"}
    finally:
        await manager.shutdown()
