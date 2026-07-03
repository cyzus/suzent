from datetime import datetime, timedelta

import pytest

import suzent.core.subagent_runner as subagent_runner
from suzent.core.subagent_runner import (
    SubAgentTask,
    _evict_old_finished_tasks,
    _task_to_sse_dict,
    _wakeup_parent_batch,
)


def _make_task(task_id: str, status: str, finished_offset: int | None = None):
    task = SubAgentTask(
        task_id=task_id,
        parent_chat_id="chat-1",
        description="x",
        tools_allowed=[],
        chat_id=f"subagent-{task_id}",
    )
    task.status = status
    if finished_offset is not None:
        task.finished_at = datetime(2026, 1, 1) + timedelta(seconds=finished_offset)
    return task


def test_evict_old_finished_tasks_keeps_active_and_recent(monkeypatch):
    monkeypatch.setattr(subagent_runner, "_MAX_FINISHED_TASKS", 3)
    subagent_runner._tasks.clear()
    try:
        # 5 finished (oldest → newest) + 2 active that must never be evicted.
        for i in range(5):
            t = _make_task(f"done_{i}", "completed", finished_offset=i)
            subagent_runner._tasks[t.task_id] = t
        for i in range(2):
            t = _make_task(f"live_{i}", "running")
            subagent_runner._tasks[t.task_id] = t

        _evict_old_finished_tasks()

        remaining = set(subagent_runner._tasks)
        # Both active tasks survive.
        assert {"live_0", "live_1"} <= remaining
        # Only the 3 newest finished tasks survive; the 2 oldest are gone.
        assert "done_0" not in remaining
        assert "done_1" not in remaining
        assert {"done_2", "done_3", "done_4"} <= remaining
    finally:
        subagent_runner._tasks.clear()


def test_evict_old_finished_tasks_noop_under_cap(monkeypatch):
    monkeypatch.setattr(subagent_runner, "_MAX_FINISHED_TASKS", 10)
    subagent_runner._tasks.clear()
    try:
        for i in range(4):
            t = _make_task(f"done_{i}", "completed", finished_offset=i)
            subagent_runner._tasks[t.task_id] = t
        _evict_old_finished_tasks()
        assert len(subagent_runner._tasks) == 4
    finally:
        subagent_runner._tasks.clear()


def test_task_to_sse_dict_includes_model_override():
    task = SubAgentTask(
        task_id="sub_1",
        parent_chat_id="chat-1",
        description="Compare options",
        tools_allowed=[],
        chat_id="subagent-sub_1",
        model_override="openai/gpt-4.1",
    )

    payload = _task_to_sse_dict(task)

    assert payload["model_override"] == "openai/gpt-4.1"


@pytest.mark.asyncio
async def test_wakeup_batch_includes_models(monkeypatch):
    captured = {}

    class FakeProcessor:
        async def process_background_turn(self, **kwargs):
            captured["system_reminders"] = kwargs["system_reminders"]
            return ""

    async def fake_wait_for_background_task_prefix(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "suzent.core.chat_processor.ChatProcessor",
        lambda: FakeProcessor(),
    )
    monkeypatch.setattr(
        "suzent.agent_manager.build_agent_config",
        lambda base_config, require_social_tool=False: base_config,
    )
    monkeypatch.setattr(
        "suzent.core.task_registry.wait_for_background_task_prefix",
        fake_wait_for_background_task_prefix,
    )

    batch = [
        SubAgentTask(
            task_id="sub_a",
            parent_chat_id="chat-1",
            description="Opinion A",
            tools_allowed=[],
            chat_id="subagent-sub_a",
            model_override="openai/gpt-4.1",
            status="completed",
            result_summary="Choose A.",
        ),
        SubAgentTask(
            task_id="sub_b",
            parent_chat_id="chat-1",
            description="Opinion B",
            tools_allowed=[],
            chat_id="subagent-sub_b",
            model_override="gemini/gemini-2.5-pro",
            status="completed",
            result_summary="Choose B.",
        ),
    ]

    await _wakeup_parent_batch("chat-1", batch)

    reminder = captured["system_reminders"][0]
    assert "Model: openai/gpt-4.1" in reminder
    assert "Model: gemini/gemini-2.5-pro" in reminder
