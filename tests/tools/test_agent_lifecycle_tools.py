from datetime import datetime, timezone
from inspect import signature
from types import SimpleNamespace

import pytest

from suzent.tools.agent_lifecycle_tools import (
    AgentListTool,
    AgentReadTool,
    AgentSendTool,
    AgentStopTool,
)
from suzent.tools.base import ToolErrorCode


def _ctx(chat_id: str = "agent-current") -> SimpleNamespace:
    return SimpleNamespace(deps=SimpleNamespace(chat_id=chat_id))


@pytest.fixture(autouse=True)
def _empty_peer_transport(monkeypatch):
    transport = SimpleNamespace(
        list_agents=lambda: [],
        peer_id=lambda agent_id: None,
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_peer_agent_transport",
        lambda: transport,
    )
    return transport


def _chat(
    chat_id: str,
    *,
    project_id: str = "project-1",
    platform: str | None = None,
    messages: list | None = None,
) -> SimpleNamespace:
    config = {"platform": platform} if platform else {}
    return SimpleNamespace(
        id=chat_id,
        title=f"Agent {chat_id}",
        project_id=project_id,
        config=config,
        messages=messages or [],
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_agent_list_recent_is_bounded_to_current_project(monkeypatch):
    current = _chat("agent-current")
    target = _chat("agent-target", platform="telegram")
    captured = {}

    class FakeDatabase:
        def get_chat(self, chat_id):
            return {current.id: current, target.id: target}.get(chat_id)

        def list_chats(self, **kwargs):
            captured.update(kwargs)
            return [SimpleNamespace(id=target.id)]

    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database", lambda: FakeDatabase()
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._agent_is_active", lambda chat_id: False
    )

    result = AgentListTool().forward(_ctx(), status="recent", limit=5)

    assert result.success
    assert captured == {"limit": 6, "project_id": "project-1"}
    assert result.metadata["agents"][0]["agent_id"] == "agent-target"
    assert result.metadata["agents"][0]["kind"] == "social"


def test_agent_list_active_uses_runtime_sessions_and_limit(monkeypatch):
    current = _chat("agent-current")
    first = _chat("agent-first")
    second = _chat("agent-second", platform="subagent")

    class FakeDatabase:
        def get_chat(self, chat_id):
            return {
                current.id: current,
                first.id: first,
                second.id: second,
            }.get(chat_id)

        def list_subagent_task_records(self, **kwargs):
            return []

    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database", lambda: FakeDatabase()
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._agent_is_active", lambda chat_id: True
    )
    from suzent.core import stream_registry

    monkeypatch.setattr(
        stream_registry, "active_stream_queues", {first.id: SimpleNamespace()}
    )
    monkeypatch.setattr(
        stream_registry, "background_queues", {second.id: SimpleNamespace()}
    )
    monkeypatch.setattr(stream_registry, "stream_controls", {})
    monkeypatch.setattr("suzent.core.subagent_runner.list_active_tasks", lambda: [])

    result = AgentListTool().forward(_ctx(), limit=1)

    assert result.success
    assert len(result.metadata["agents"]) == 1
    assert result.metadata["has_more"] is True


def test_agent_list_includes_paired_remote_agents(monkeypatch, _empty_peer_transport):
    current = _chat("agent-current")

    class FakeDatabase:
        def get_chat(self, chat_id):
            return current if chat_id == current.id else None

        def list_chats(self, **kwargs):
            return [SimpleNamespace(id=current.id)]

    _empty_peer_transport.list_agents = lambda: [
        {
            "agent_id": "peer:peer-1",
            "title": "Laptop",
            "kind": "remote",
            "status": "ready",
            "project_id": None,
            "parent_agent_id": None,
            "updated_at": None,
        }
    ]
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database", lambda: FakeDatabase()
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._agent_is_active", lambda chat_id: False
    )

    result = AgentListTool().forward(_ctx(), status="recent")

    assert result.success
    assert any(
        record["agent_id"] == "peer:peer-1" for record in result.metadata["agents"]
    )


def test_agent_list_active_excludes_paused_remote_agents(
    monkeypatch, _empty_peer_transport
):
    current = _chat("agent-current")
    _empty_peer_transport.list_agents = lambda: [
        {
            "agent_id": "peer:ready",
            "title": "Ready",
            "kind": "remote",
            "status": "ready",
            "updated_at": None,
        },
        {
            "agent_id": "peer:paused",
            "title": "Paused",
            "kind": "remote",
            "status": "paused",
            "updated_at": None,
        },
    ]
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: current),
    )
    from suzent.core import stream_registry

    monkeypatch.setattr(stream_registry, "active_stream_queues", {})
    monkeypatch.setattr(stream_registry, "background_queues", {})
    monkeypatch.setattr(stream_registry, "stream_controls", {})
    monkeypatch.setattr("suzent.core.subagent_runner.list_active_tasks", lambda: [])

    result = AgentListTool().forward(_ctx(), status="active")

    assert [agent["agent_id"] for agent in result.metadata["agents"]] == ["peer:ready"]


@pytest.mark.asyncio
async def test_agent_read_returns_sanitized_visible_transcript(monkeypatch):
    target = _chat(
        "agent-target",
        messages=[
            {"role": "user", "content": "Inspect code"},
            {
                "role": "assistant",
                "parts": [
                    {"type": "reasoning", "text": "private reasoning"},
                    {"type": "text", "text": "Inspection complete."},
                ],
            },
        ],
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._accessible_agent",
        lambda agent_id, current_chat_id: target,
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._agent_is_active", lambda chat_id: False
    )

    result = await AgentReadTool().forward(_ctx(), "agent-target")

    assert result.success
    assert "Inspection complete." in result.message
    assert "private reasoning" not in result.message
    assert result.metadata["message_count"] == 2


@pytest.mark.asyncio
async def test_agent_read_bounds_large_transcripts_without_more_arguments(monkeypatch):
    target = _chat(
        "agent-target",
        messages=[
            {"role": "user", "content": f"message-{index}-" + "x" * 30}
            for index in range(10)
        ],
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._accessible_agent",
        lambda agent_id, current_chat_id: target,
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._agent_is_active", lambda chat_id: False
    )
    monkeypatch.setattr("suzent.tools.agent_lifecycle_tools._MAX_TRANSCRIPT_CHARS", 100)

    result = await AgentReadTool().forward(_ctx(), "agent-target")

    assert result.success
    assert "earlier messages omitted" in result.message
    assert "message-9" in result.message
    assert "message-0" not in result.message
    assert result.metadata["transcript_truncated"] is True


@pytest.mark.asyncio
async def test_agent_read_rejects_agent_from_another_project(monkeypatch):
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._accessible_agent",
        lambda agent_id, current_chat_id: None,
    )

    result = await AgentReadTool().forward(_ctx(), "agent-other")

    assert not result.success
    assert result.error_code == ToolErrorCode.FILE_NOT_FOUND


@pytest.mark.asyncio
async def test_agent_read_fetches_peer_owned_transcript(
    monkeypatch, _empty_peer_transport
):
    current = _chat("agent-current")
    _empty_peer_transport.peer_id = lambda agent_id: "peer-1"

    async def read(agent_id):
        return {
            "status": "idle",
            "messages": [{"role": "assistant", "text": "Remote result"}],
            "message_count": 1,
        }

    _empty_peer_transport.read = read
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: current),
    )

    result = await AgentReadTool().forward(_ctx(), "peer:peer-1")

    assert result.success
    assert "Remote result" in result.message
    assert result.metadata["kind"] == "remote"


def test_agent_send_queues_durable_message(monkeypatch):
    target = _chat("agent-target")
    captured = {}
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._accessible_agent",
        lambda agent_id, current_chat_id: target,
    )

    def enqueue(**kwargs):
        captured.update(kwargs)
        return {"message_id": "msg-1", "status": "pending"}, True

    monkeypatch.setattr("suzent.core.agent_inbox.enqueue_agent_message", enqueue)

    result = AgentSendTool().forward(_ctx(), "agent-target", "Please verify this")

    assert result.success
    assert captured == {
        "sender_chat_id": "agent-current",
        "target_chat_id": "agent-target",
        "content": "Please verify this",
    }
    assert result.metadata["message_id"] == "msg-1"


def test_agent_send_schema_stays_minimal():
    assert list(signature(AgentSendTool.forward).parameters) == [
        "self",
        "ctx",
        "agent_id",
        "message",
    ]


def test_agent_send_rejects_self_delivery(monkeypatch):
    current = _chat("agent-current")
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._accessible_agent",
        lambda agent_id, current_chat_id: current,
    )

    result = AgentSendTool().forward(_ctx(), "agent-current", "Continue")

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT


def test_agent_send_queues_peer_transport_message(monkeypatch, _empty_peer_transport):
    current = _chat("agent-current")
    captured = {}
    _empty_peer_transport.peer_id = lambda agent_id: "peer-1"

    def enqueue(**kwargs):
        captured.update(kwargs)
        return {"message_id": "msg-remote", "status": "pending"}, True

    _empty_peer_transport.enqueue = enqueue
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: current),
    )

    result = AgentSendTool().forward(_ctx(), "peer:peer-1", "Run remote checks")

    assert result.success
    assert captured == {
        "agent_id": "peer:peer-1",
        "sender_chat_id": "agent-current",
        "content": "Run remote checks",
    }
    assert result.metadata["transport"] == "suzent_peer"


@pytest.mark.asyncio
async def test_agent_stop_stops_active_subagent(monkeypatch):
    target = _chat("subagent-sub_a", platform="subagent")
    task = SimpleNamespace(task_id="sub_a", chat_id=target.id)
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._accessible_agent",
        lambda agent_id, current_chat_id: target,
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._agent_is_active", lambda chat_id: True
    )
    monkeypatch.setattr("suzent.core.subagent_runner.list_active_tasks", lambda: [task])
    stopped = []

    async def stop_subagent(task_id):
        stopped.append(task_id)
        return True

    monkeypatch.setattr("suzent.core.subagent_runner.stop_subagent", stop_subagent)

    result = await AgentStopTool().forward(_ctx(), target.id)

    assert result.success
    assert stopped == ["sub_a"]


@pytest.mark.asyncio
async def test_agent_stop_requests_peer_cancellation(
    monkeypatch, _empty_peer_transport
):
    current = _chat("agent-current")
    stopped = []
    _empty_peer_transport.peer_id = lambda agent_id: "peer-1"

    async def stop(agent_id):
        stopped.append(agent_id)
        return True

    _empty_peer_transport.stop = stop
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: current),
    )

    result = await AgentStopTool().forward(_ctx(), "peer:peer-1")

    assert result.success
    assert stopped == ["peer:peer-1"]
