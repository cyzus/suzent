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


def test_agent_read_returns_sanitized_visible_transcript(monkeypatch):
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

    result = AgentReadTool().forward(_ctx(), "agent-target")

    assert result.success
    assert "Inspection complete." in result.message
    assert "private reasoning" not in result.message
    assert result.metadata["message_count"] == 2


def test_agent_read_bounds_large_transcripts_without_more_arguments(monkeypatch):
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

    result = AgentReadTool().forward(_ctx(), "agent-target")

    assert result.success
    assert "earlier messages omitted" in result.message
    assert "message-9" in result.message
    assert "message-0" not in result.message
    assert result.metadata["transcript_truncated"] is True


def test_agent_read_rejects_agent_from_another_project(monkeypatch):
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._accessible_agent",
        lambda agent_id, current_chat_id: None,
    )

    result = AgentReadTool().forward(_ctx(), "agent-other")

    assert not result.success
    assert result.error_code == ToolErrorCode.FILE_NOT_FOUND


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
