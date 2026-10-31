import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import suzent.core.subagent_runner as subagent_runner
from suzent.core.subagent_runner import (
    SubAgentTask,
    _evict_old_finished_tasks,
    _evict_old_finished_tasks_locked,
    _queue_parent_wakeup,
    _task_to_sse_dict,
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
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


@pytest.mark.asyncio
async def test_cancelled_setup_explains_itself(monkeypatch):
    """A bare cancel must still say why, not just "cancelled"."""
    task = _make_task("sub_cancel", "queued")
    subagent_runner._tasks[task.task_id] = task

    def cancel_now():
        raise asyncio.CancelledError()

    monkeypatch.setattr("suzent.core.providers.get_default_chat_model", cancel_now)
    monkeypatch.setattr(subagent_runner, "_persist_task_state", lambda task: None)

    try:
        with pytest.raises(asyncio.CancelledError):
            await subagent_runner._run_subagent(task)

        assert task.status == "cancelled"
        assert task.error and task.error != "Sub-agent cancelled"
        assert "Stopped" in task.error
        assert task.finished_at is not None
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


@pytest.mark.asyncio
async def test_cancellation_reason_names_a_shutdown(monkeypatch):
    from suzent.core import task_registry

    task = _make_task("sub_shutdown", "running")
    monkeypatch.setattr(
        type(task_registry.get_task_registry()),
        "is_shutting_down",
        property(lambda self: True),
    )

    assert "shut down" in subagent_runner._cancellation_reason(task)


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
        # A stop is not a failure: it gets its own state so the UI can say
        # "stopped" in neutral colours instead of showing a red error.
        assert task.status == "cancelled"
        assert task.error == "Stopped by you"
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
        assert task.status == "cancelled"
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


def test_parent_wakeup_is_persisted_with_model(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "suzent.core.agent_inbox.enqueue_agent_message",
        lambda **kwargs: captured.update(kwargs),
    )
    task = SubAgentTask(
        task_id="sub_a",
        parent_chat_id="chat-1",
        description="Opinion A",
        tools_allowed=[],
        chat_id="subagent-sub_a",
        model_override="openai/gpt-4.1",
        status="completed",
        result_summary="Choose A.",
        citation_sources=[
            {
                "id": "sa_sub_a_src_1",
                "type": "webpage",
                "title": "Evidence",
                "url": "https://example.com/evidence",
            }
        ],
    )

    _queue_parent_wakeup(task)

    assert captured["message_id"] == "subagent-result-sub_a"
    assert captured["sender_chat_id"] == "subagent-sub_a"
    assert captured["target_chat_id"] == "chat-1"
    assert captured["kind"] == "subagent_result"
    assert captured["payload"]["task_id"] == "sub_a"
    assert captured["payload"]["status"] == "completed"
    assert captured["payload"]["citation_sources"][0]["id"] == "sa_sub_a_src_1"
    assert "Model: openai/gpt-4.1" in captured["content"]
    assert "Choose A." in captured["content"]
    assert "[sa_sub_a_src_1] Evidence" in captured["content"]


def _fake_db(chat):
    return SimpleNamespace(get_chat=lambda chat_id: chat)


@pytest.mark.parametrize(
    ("parent_model", "expected"),
    [("parent/model", "parent/model"), (None, "default/model")],
)
@pytest.mark.asyncio
async def test_subagent_defaults_to_parent_model(monkeypatch, parent_model, expected):
    """Without inherit_context too: the catalog default is only a fallback."""
    task = _make_task(f"sub_model_{expected[0]}", "queued")
    subagent_runner._tasks[task.task_id] = task

    def stop_after_model_resolution(task):
        raise RuntimeError("stop")

    monkeypatch.setattr(subagent_runner, "_parent_model_id", lambda _: parent_model)
    monkeypatch.setattr(
        "suzent.core.providers.get_default_chat_model", lambda: "default/model"
    )
    monkeypatch.setattr(subagent_runner, "_persist_task_state", lambda task: None)
    monkeypatch.setattr(
        subagent_runner, "_ensure_task_chat", stop_after_model_resolution
    )

    try:
        await subagent_runner._run_subagent(task, wakeup_parent=False)

        assert task.model_override == expected
    finally:
        subagent_runner._tasks.pop(task.task_id, None)


def test_parent_model_id_prefers_model_history_ran_on(monkeypatch):
    chat = SimpleNamespace(agent_state=b"state", config={"model": "configured/model"})
    monkeypatch.setattr("suzent.database.get_database", lambda: _fake_db(chat))
    monkeypatch.setattr(
        "suzent.core.agent_serializer.deserialize_state",
        lambda state: {"model_id": "ran/model"},
    )

    assert subagent_runner._parent_model_id("chat-1") == "ran/model"


def test_parent_model_id_falls_back_to_configured_model(monkeypatch):
    chat = SimpleNamespace(agent_state=None, config={"model": "configured/model"})
    monkeypatch.setattr("suzent.database.get_database", lambda: _fake_db(chat))

    assert subagent_runner._parent_model_id("chat-1") == "configured/model"


def test_parent_model_id_is_none_without_parent(monkeypatch):
    monkeypatch.setattr("suzent.database.get_database", lambda: _fake_db(None))

    assert subagent_runner._parent_model_id("gone") is None


def _fork_task(task_id: str, parent: str, **fields) -> SubAgentTask:
    return SubAgentTask(
        task_id=task_id,
        parent_chat_id=parent,
        description="look into it",
        tools_allowed=fields.pop("tools_allowed", []),
        chat_id=f"subagent-{task_id}",
        inherit_context=True,
        **fields,
    )


def _record_parent_turn(parent: str, config: dict, model_id: str | None = None) -> None:
    from suzent.core import prompt_cache

    prompt_cache.record_turn_config(parent, config, model_id)
    prompt_cache._remember(
        prompt_cache._LATEST_PREFIXES,
        parent,
        prompt_cache.PrefixSnapshot(instruction_parts=(), tool_defs=()),
    )


_PARENT_TURN = {
    "_chat_id": "parent",
    "_project_context_dir": "/p",
    "model": "claude-opus-5-5",
    "tools": ["WebSearchTool", "BashTool", "AgentTool"],
    "thinking": "high",
    "permission_mode": "default",
    "memory_enabled": True,
    "cwd": "/repo",
}


def test_fork_config_keeps_the_parents_tools_and_holds_calls_to_its_own():
    _record_parent_turn("parent-fc", _PARENT_TURN)
    task = _fork_task("fc", "parent-fc", tools_allowed=["WebSearchTool"])
    base = {
        "permission_mode": "auto",
        "interaction_profile": "subagent",
        "memory_enabled": False,
        "platform": "subagent",
        "static_instructions": "sub-agent prompt",
        "model": "claude-opus-5-5",
        "tools": ["WebSearchTool"],
    }

    config = subagent_runner.fork_turn_config(task, base)

    assert config["tools"] == _PARENT_TURN["tools"]
    assert config["thinking"] == "high"
    assert "static_instructions" not in config
    assert not any(key.startswith("_") for key in config)
    assert config["permission_mode"] == "auto"
    assert config["memory_enabled"] is False
    assert "cwd" not in config
    assert config["call_allowed_tools"] == ["WebSearchTool"]
    assert config["prompt_cache_chat_id"] == "parent-fc"


def test_fork_without_a_tool_list_still_cannot_spawn_agents():
    _record_parent_turn("parent-nt", _PARENT_TURN)
    task = _fork_task("nt", "parent-nt")

    config = subagent_runner.fork_turn_config(task, {"model": "claude-opus-5-5"})

    assert config["call_allowed_tools"] == ["WebSearchTool", "BashTool"]


def test_fork_falls_back_without_a_recorded_parent_or_on_another_model():
    _record_parent_turn("parent-fb", _PARENT_TURN)

    assert (
        subagent_runner.fork_turn_config(_fork_task("fb1", "parent-unknown"), {})
        is None
    )
    assert (
        subagent_runner.fork_turn_config(
            _fork_task("fb2", "parent-fb"), {"model": "gpt-5.6"}
        )
        is None
    )


def test_fork_matches_a_parent_whose_model_was_resolved_by_default():
    parent_turn = {k: v for k, v in _PARENT_TURN.items() if k != "model"}
    _record_parent_turn("parent-dm", parent_turn, model_id="claude-opus-5-5")

    config = subagent_runner.fork_turn_config(
        _fork_task("dm", "parent-dm"), {"model": "claude-opus-5-5"}
    )

    assert config is not None
    assert "model" not in config
    assert "_model_id" not in config


def test_fork_reminder_carries_role_tools_and_a_moved_cwd():
    task = _fork_task("rm", "parent-rm", subagent_type="explore")
    config = {"call_allowed_tools": ["GrepTool"], "cwd": "/worktree"}

    reminder = subagent_runner.fork_reminder(task, config, parent_cwd="/repo")

    assert "code-search sub-agent" in reminder
    assert "GrepTool" in reminder
    assert "/worktree" in reminder
    assert "/worktree" not in subagent_runner.fork_reminder(
        task, config, parent_cwd="/worktree"
    )


@pytest.mark.asyncio
async def test_a_subagent_without_tools_cannot_fall_back_to_spawning_agents():
    """An empty tool list resolves to the user's defaults, which hold AgentTool."""
    from unittest.mock import AsyncMock, MagicMock, patch

    task = SubAgentTask(
        task_id="sub_empty",
        parent_chat_id="parent",
        chat_id="subagent-sub_empty",
        description="do a thing",
        tools_allowed=[],
        model_override="parent/model",
    )
    db = MagicMock()
    db.get_chat.return_value = MagicMock(
        config={"denied_tools": ["RunCommandTool"]},
        working_directory=None,
        project_id=None,
    )
    built: list[dict] = []

    with (
        patch(
            "suzent.agent_manager.build_agent_config",
            lambda config, **_: built.append(dict(config)) or config,
        ),
        patch(
            "suzent.core.chat_processor.ChatProcessor.process_turn_text",
            AsyncMock(return_value="done"),
        ),
        patch.object(subagent_runner, "_ensure_task_chat", return_value=db),
        patch.object(subagent_runner, "register_background_stream", MagicMock()),
        patch.object(subagent_runner, "unregister_background_stream", MagicMock()),
        patch.object(subagent_runner, "_broadcast_task_update", MagicMock()),
        patch.object(subagent_runner, "_persist_task_state", MagicMock()),
        patch.object(subagent_runner, "_evict_old_finished_tasks_locked", AsyncMock()),
        patch.object(subagent_runner, "_notify_parent", AsyncMock()),
        patch.object(subagent_runner, "_queue_parent_wakeup", MagicMock()),
    ):
        await subagent_runner._run_subagent(task, wakeup_parent=False)

    assert task.status == "completed", task.error
    denied = set(built[0]["denied_tools"])
    assert {"RunCommandTool", "AgentTool", "AgentSendTool"} <= denied
    persisted = db.merge_chat_config.call_args.args[1]
    assert "AgentTool" in persisted["denied_tools"]
