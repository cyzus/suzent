from types import SimpleNamespace

import pytest

from suzent.core.subagent_runner import SubAgentTask
from suzent.tools.agent_lifecycle_tools import (
    AgentListTool,
    AgentReadTool,
    AgentStopTool,
    AgentWaitTool,
)
from suzent.tools.base import ToolErrorCode


def _ctx(chat_id: str = "parent-chat") -> SimpleNamespace:
    return SimpleNamespace(deps=SimpleNamespace(chat_id=chat_id))


def _task(task_id: str, status: str = "running") -> SubAgentTask:
    return SubAgentTask(
        task_id=task_id,
        parent_chat_id="parent-chat",
        description=f"Task {task_id}",
        tools_allowed=[],
        status=status,
        chat_id=f"subagent-{task_id}",
    )


def test_agent_list_defaults_to_bounded_active_tasks(monkeypatch):
    tasks = [_task("sub_a"), _task("sub_b"), _task("sub_done", "completed")]
    monkeypatch.setattr(
        "suzent.core.subagent_runner.list_all_tasks", lambda parent_chat_id: tasks
    )

    result = AgentListTool().forward(_ctx(), limit=1)

    assert result.success
    assert [task["task_id"] for task in result.metadata["tasks"]] == ["sub_a"]
    assert result.metadata["has_more"] is True
    assert "sub_done" not in result.message


def test_agent_list_recent_queries_only_current_parent(monkeypatch):
    captured = {}

    class FakeDatabase:
        def list_subagent_task_records(self, **kwargs):
            captured.update(kwargs)
            return [
                {
                    "task_id": "sub_old",
                    "parent_chat_id": "parent-chat",
                    "chat_id": "subagent-sub_old",
                    "description": "Old task",
                    "status": "completed",
                    "result_summary": "done",
                    "error": None,
                    "model_override": None,
                    "started_at": "2026-01-01T00:00:00",
                    "finished_at": "2026-01-01T00:01:00",
                }
            ]

    monkeypatch.setattr(
        "suzent.core.subagent_runner.list_all_tasks", lambda parent_chat_id: []
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database", lambda: FakeDatabase()
    )

    result = AgentListTool().forward(_ctx(), status="recent", limit=5)

    assert result.success
    assert captured == {"parent_chat_id": "parent-chat", "limit": 6}
    assert result.metadata["tasks"][0]["task_id"] == "sub_old"


def test_agent_read_returns_sanitized_visible_transcript(monkeypatch):
    record = {
        "task_id": "sub_a",
        "parent_chat_id": "parent-chat",
        "chat_id": "subagent-sub_a",
        "description": "Inspect code",
        "status": "completed",
        "result_summary": "done",
        "error": None,
        "model_override": None,
    }
    chat = SimpleNamespace(
        messages=[
            {"role": "user", "content": "Inspect code"},
            {
                "role": "assistant",
                "parts": [
                    {"type": "reasoning", "text": "private reasoning"},
                    {"type": "text", "text": "Inspection complete."},
                ],
            },
        ]
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._find_accessible_task",
        lambda task_id, current_chat_id: (record, None),
    )
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools.get_database",
        lambda: SimpleNamespace(get_chat=lambda chat_id: chat),
    )

    result = AgentReadTool().forward(_ctx(), "sub_a")

    assert result.success
    assert "Inspection complete." in result.message
    assert "private reasoning" not in result.message
    assert result.metadata["message_count"] == 2


def test_agent_read_rejects_task_owned_by_another_chat(monkeypatch):
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._find_accessible_task",
        lambda task_id, current_chat_id: None,
    )

    result = AgentReadTool().forward(_ctx(), "sub_other")

    assert not result.success
    assert result.error_code == ToolErrorCode.FILE_NOT_FOUND


@pytest.mark.asyncio
async def test_agent_wait_returns_after_runtime_task_finishes(monkeypatch):
    task = _task("sub_a")

    def find_task(task_id, current_chat_id):
        return (
            {
                "task_id": task.task_id,
                "parent_chat_id": task.parent_chat_id,
                "chat_id": task.chat_id,
                "description": task.description,
                "status": task.status,
                "result_summary": task.result_summary,
                "error": task.error,
                "model_override": task.model_override,
                "started_at": None,
                "finished_at": None,
            },
            task,
        )

    async def wait_for_subagents(task_ids, timeout_seconds):
        task.status = "completed"
        return [task], False

    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._find_accessible_task", find_task
    )
    monkeypatch.setattr(
        "suzent.core.subagent_runner.wait_for_subagents", wait_for_subagents
    )

    result = await AgentWaitTool().forward(_ctx(), ["sub_a"], timeout_seconds=1)

    assert result.success
    assert result.metadata["timed_out"] is False
    assert result.metadata["tasks"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_stop_stops_owned_runtime_task(monkeypatch):
    task = _task("sub_a")
    monkeypatch.setattr(
        "suzent.tools.agent_lifecycle_tools._find_accessible_task",
        lambda task_id, current_chat_id: (
            {
                "task_id": task.task_id,
                "parent_chat_id": task.parent_chat_id,
                "chat_id": task.chat_id,
                "description": task.description,
                "status": task.status,
            },
            task,
        ),
    )
    stopped = []

    async def stop_subagent(task_id):
        stopped.append(task_id)
        return True

    monkeypatch.setattr("suzent.core.subagent_runner.stop_subagent", stop_subagent)

    result = await AgentStopTool().forward(_ctx(), "sub_a")

    assert result.success
    assert stopped == ["sub_a"]
