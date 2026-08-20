"""
End-to-end federation: our own A2A client driving our own A2A server.

This is the loop that matters for interop — the client half and the server half
are written against the spec, not against each other, so pointing one at the
other exercises the actual wire format rather than a shared shortcut.
"""

import json

import httpx
import pytest

from suzent.a2a import tasks as tasks_module
from suzent.a2a.client import (
    A2AClient,
    A2AClientError,
    fetch_agent_card,
    summarize_task,
)
from suzent.a2a.outbound import OutboundTaskTracker
from suzent.a2a.store import A2AAgentStore
from suzent.a2a.types import Task, TaskState
from suzent.config import CONFIG
from suzent.server import app


@pytest.fixture(autouse=True)
def _fresh_task_store(monkeypatch):
    monkeypatch.setattr(tasks_module, "_store", tasks_module.TaskStore())


@pytest.fixture(autouse=True)
def _published(monkeypatch):
    monkeypatch.setattr(CONFIG, "a2a_enabled", True, raising=False)


@pytest.fixture
def transport():
    """Drives the real Starlette app in-process, over real httpx machinery."""
    return httpx.ASGITransport(app=app)


class _FakeProcessor:
    frames: list[str] = []

    def process_turn(self, **_kwargs):
        async def _gen():
            for frame in self.frames:
                yield frame

        return _gen()


@pytest.fixture
def stub_agent(monkeypatch):
    def _install(frames):
        import suzent.agent_manager as agent_manager
        import suzent.core.chat_processor as chat_processor
        import suzent.database as database

        _FakeProcessor.frames = frames
        monkeypatch.setattr(chat_processor, "ChatProcessor", _FakeProcessor)
        monkeypatch.setattr(
            agent_manager, "build_agent_config", lambda *a, **k: {}, raising=False
        )

        class _FakeDB:
            def ensure_channel_chat(self, *a, **k):
                return True

        monkeypatch.setattr(database, "get_database", lambda: _FakeDB(), raising=False)

    return _install


def _frame(delta: str) -> str:
    return f"data: {json.dumps({'type': 'TEXT_MESSAGE_CONTENT', 'delta': delta})}\n\n"


@pytest.mark.asyncio
async def test_card_discovery_round_trip(transport):
    card, base_url, rpc_url = await fetch_agent_card(
        "http://testserver", transport=transport
    )

    assert card["protocolVersion"] == "0.3.0"
    assert base_url == "http://testserver"
    # The card's own url field decides where RPCs go.
    assert rpc_url.endswith("/a2a/v1")


@pytest.mark.asyncio
async def test_missing_card_gives_an_actionable_error(transport, monkeypatch):
    monkeypatch.setattr(CONFIG, "a2a_enabled", False, raising=False)

    with pytest.raises(A2AClientError) as excinfo:
        await fetch_agent_card("http://testserver", transport=transport)

    assert "has not published a card" in str(excinfo.value)


@pytest.mark.asyncio
async def test_delegate_a_task_and_read_the_answer(transport, stub_agent):
    stub_agent([_frame("The answer "), _frame("is 42.")])
    client = A2AClient("http://testserver/a2a/v1", transport=transport)

    result = await client.send("what is the answer?")

    assert isinstance(result, Task)
    assert result.status.state is TaskState.completed
    assert summarize_task(result) == "The answer is 42."


@pytest.mark.asyncio
async def test_tasks_get_after_delegation(transport, stub_agent):
    stub_agent([_frame("done")])
    client = A2AClient("http://testserver/a2a/v1", transport=transport)

    sent = await client.send("go")
    fetched = await client.get_task(sent.id)

    assert fetched.id == sent.id
    assert fetched.status.state is TaskState.completed


@pytest.mark.asyncio
async def test_streaming_delegation_yields_lifecycle_events(transport, stub_agent):
    stub_agent([_frame("chunk one "), _frame("chunk two")])
    client = A2AClient("http://testserver/a2a/v1", transport=transport)

    kinds, text = [], ""
    async for event in client.stream("go"):
        kinds.append(getattr(event, "kind", None))
        if getattr(event, "kind", None) == "artifact-update":
            text += event.artifact.parts[0].text

    assert "status-update" in kinds
    assert text == "chunk one chunk two"


@pytest.mark.asyncio
async def test_unreachable_agent_is_reported_not_raised_raw():
    client = A2AClient("http://127.0.0.1:9/a2a/v1")

    with pytest.raises(A2AClientError) as excinfo:
        await client.send("hello")

    assert "Could not reach remote agent" in str(excinfo.value)


# ─── Registry + outbound tracking ────────────────────────────────────


def test_agent_store_keeps_token_across_refresh(tmp_path):
    store = A2AAgentStore(path=tmp_path / "agents.json")
    agent_id = store.add(
        base_url="https://a.example",
        rpc_url="https://a.example/a2a/v1",
        name="Research Bot",
        token="secret-token",
    )
    # A refresh re-adds without a token; the stored credential must survive.
    store.add(
        base_url="https://a.example",
        rpc_url="https://a.example/a2a/v1",
        name="Research Bot v2",
    )

    assert store.get(agent_id)["token"] == "secret-token"
    assert store.get(agent_id)["name"] == "Research Bot v2"
    # Listing never leaks the token itself.
    listed = store.list_agents()[0]
    assert "token" not in listed and listed["has_token"] is True


def test_outbound_tracker_prefers_evicting_settled_tasks():
    tracker = OutboundTaskTracker(max_tracked=2)

    def _task(task_id: str, state: TaskState) -> Task:
        return Task.model_validate(
            {
                "kind": "task",
                "id": task_id,
                "contextId": "ctx",
                "status": {"state": state.value},
            }
        )

    tracker.record(agent_id="a", agent_name="A", task=_task("live", TaskState.working))
    for index in range(3):
        tracker.record(
            agent_id="a",
            agent_name="A",
            task=_task(f"done{index}", TaskState.completed),
        )

    assert tracker.get("a", "live") is not None


def test_outbound_tracker_forgets_removed_agent():
    tracker = OutboundTaskTracker()
    task = Task.model_validate(
        {"kind": "task", "id": "t1", "contextId": "c", "status": {"state": "working"}}
    )
    tracker.record(agent_id="gone", agent_name="Gone", task=task)

    tracker.forget_agent("gone")

    assert tracker.list_tasks() == []
