import json
from types import SimpleNamespace

import pytest

from suzent.routes import subagent_routes


def _record(task_id: str, status: str = "completed") -> dict:
    return {
        "task_id": task_id,
        "parent_chat_id": "parent-chat",
        "chat_id": f"subagent-{task_id}",
        "description": f"Task {task_id}",
        "tools_allowed": [],
        "status": status,
        "result_summary": "done",
        "error": None,
        "model_override": None,
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:01:00",
    }


@pytest.mark.asyncio
async def test_list_subagents_applies_bounded_database_query(monkeypatch):
    captured = {}

    class FakeDatabase:
        def list_subagent_task_records(self, **kwargs):
            captured.update(kwargs)
            return [_record("sub_1"), _record("sub_2"), _record("sub_3")]

    monkeypatch.setattr(subagent_routes, "list_all_tasks", lambda **kwargs: [])
    monkeypatch.setattr(subagent_routes, "get_database", lambda: FakeDatabase())
    request = SimpleNamespace(
        query_params={"parent_chat_id": "parent-chat", "limit": "2"}
    )

    response = await subagent_routes.list_subagents(request)
    payload = json.loads(response.body)

    assert captured == {"parent_chat_id": "parent-chat", "limit": 3}
    assert len(payload["tasks"]) == 2
    assert payload["has_more"] is True
    assert payload["limit"] == 2


@pytest.mark.asyncio
async def test_get_subagent_queries_one_persisted_task(monkeypatch):
    captured = {}

    class FakeDatabase:
        def list_subagent_task_records(self, **kwargs):
            captured.update(kwargs)
            return [_record("sub_target")]

    monkeypatch.setattr(subagent_routes, "get_task", lambda task_id: None)
    monkeypatch.setattr(subagent_routes, "get_database", lambda: FakeDatabase())
    request = SimpleNamespace(path_params={"task_id": "sub_target"})

    response = await subagent_routes.get_subagent(request)
    payload = json.loads(response.body)

    assert captured == {"task_id": "sub_target", "limit": 1}
    assert payload["task"]["task_id"] == "sub_target"


@pytest.mark.asyncio
async def test_list_subagents_clamps_invalid_and_excessive_limits(monkeypatch):
    captured_limits = []

    class FakeDatabase:
        def list_subagent_task_records(self, **kwargs):
            captured_limits.append(kwargs["limit"])
            return []

    monkeypatch.setattr(subagent_routes, "list_all_tasks", lambda **kwargs: [])
    monkeypatch.setattr(subagent_routes, "get_database", lambda: FakeDatabase())

    for raw_limit in ("invalid", "1000", "0"):
        request = SimpleNamespace(query_params={"limit": raw_limit})
        await subagent_routes.list_subagents(request)

    assert captured_limits == [101, 201, 2]
