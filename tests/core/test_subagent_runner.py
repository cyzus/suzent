from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import suzent.core.subagent_runner as subagent_runner
from suzent.core.subagent_runner import (
    SubAgentTask,
    _evict_old_finished_tasks,
    _evict_old_finished_tasks_locked,
    _task_to_sse_dict,
    _wakeup_parent_batch,
    clear_stuck_tasks,
    spawn_subagent,
    stop_subagent,
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


@pytest.mark.asyncio
async def test_background_subagent_uses_shared_task_registry(monkeypatch):
    captured = {}

    async def fake_register(coro, task_id, description):
        captured.update(task_id=task_id, description=description)
        coro.close()
        return SimpleNamespace(done=lambda: False, cancel=lambda: None)

    monkeypatch.setattr(subagent_runner, "_resolve_tool_names", lambda tools: ([], []))
    monkeypatch.setattr(subagent_runner, "_ensure_task_chat", lambda task: None)
    monkeypatch.setattr(subagent_runner, "_persist_task_state", lambda task: None)
    monkeypatch.setattr(
        "suzent.core.task_registry.register_background_task", fake_register
    )

    task = await spawn_subagent(
        parent_chat_id="chat-1",
        description="Inspect the repository",
        tools_allowed=[],
        run_in_background=True,
    )

    try:
        assert captured == {
            "task_id": f"subagent_{task.task_id}",
            "description": "Inspect the repository",
        }
        assert task.runner_task is not None
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


@pytest.mark.asyncio
async def test_spawn_subagent_reports_persistence_failure_without_scheduling(
    monkeypatch,
):
    registered = []
    monkeypatch.setattr(subagent_runner, "_resolve_tool_names", lambda tools: ([], []))

    def fail_persistence(task):
        raise RuntimeError("database unavailable")

    async def fake_register(*args, **kwargs):
        registered.append(True)

    monkeypatch.setattr(subagent_runner, "_ensure_task_chat", fail_persistence)
    monkeypatch.setattr(
        "suzent.core.task_registry.register_background_task", fake_register
    )

    task = await spawn_subagent(
        parent_chat_id="chat-1",
        description="Inspect the repository",
        tools_allowed=[],
        run_in_background=True,
    )

    try:
        assert task.status == "failed"
        assert task.error == "database unavailable"
        assert registered == []
        assert task.completion_event.is_set()
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


@pytest.mark.asyncio
async def test_subagent_setup_failure_reaches_terminal_state(monkeypatch):
    task = _make_task("sub_setup", "queued")
    subagent_runner._tasks[task.task_id] = task

    def fail_model():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        "suzent.core.providers.get_default_chat_model",
        fail_model,
    )
    monkeypatch.setattr(subagent_runner, "_persist_task_state", lambda task: None)

    try:
        await subagent_runner._run_subagent(task)

        assert task.status == "failed"
        assert task.error == "model unavailable"
        assert task.finished_at is not None
        assert task.completion_event.is_set()
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


@pytest.mark.asyncio
async def test_stop_subagent_cancels_runner_and_rejects_terminal_retry(monkeypatch):
    cancelled = []
    stopped_streams = []
    task = _make_task("sub_stop", "running")
    task.runner_task = SimpleNamespace(
        done=lambda: False, cancel=lambda: cancelled.append(task.task_id)
    )
    subagent_runner._tasks[task.task_id] = task
    monkeypatch.setattr(
        "suzent.core.stream_registry.stop_stream",
        lambda chat_id, reason: stopped_streams.append((chat_id, reason)),
    )
    monkeypatch.setattr(subagent_runner, "_persist_task_state", lambda task: None)

    try:
        assert await stop_subagent(task.task_id) is True
        assert await stop_subagent(task.task_id) is False
        assert task.status == "failed"
        assert cancelled == [task.task_id]
        assert stopped_streams[0][0] == task.chat_id
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


@pytest.mark.asyncio
async def test_clear_stuck_tasks_cancels_registered_runners(monkeypatch):
    cancelled = []
    task = _make_task("sub_stuck", "queued")
    task.runner_task = SimpleNamespace(
        done=lambda: False, cancel=lambda: cancelled.append(task.task_id)
    )
    subagent_runner._tasks[task.task_id] = task
    monkeypatch.setattr(
        "suzent.core.stream_registry.stop_stream", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(subagent_runner, "_persist_task_state", lambda task: None)

    try:
        assert await clear_stuck_tasks() == [task.task_id]
        assert task.status == "failed"
        assert cancelled == [task.task_id]
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


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


@pytest.mark.asyncio
async def test_evict_on_terminal_prunes_burst_that_finishes(monkeypatch):
    # Simulates the burst case: many subagents were queued (so registration-time
    # eviction saw them as active), then all transition to finished with no new
    # spawn. The terminal-transition prune must still cap the registry.
    monkeypatch.setattr(subagent_runner, "_MAX_FINISHED_TASKS", 3)
    subagent_runner._tasks.clear()
    try:
        for i in range(6):
            t = _make_task(f"done_{i}", "completed", finished_offset=i)
            subagent_runner._tasks[t.task_id] = t

        await _evict_old_finished_tasks_locked()

        remaining = set(subagent_runner._tasks)
        assert len(remaining) == 3
        assert {"done_3", "done_4", "done_5"} == remaining
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
