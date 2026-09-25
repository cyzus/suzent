import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from suzent.core.background_commands import BackgroundCommands


@pytest.fixture
def commands(monkeypatch):
    registry = BackgroundCommands()
    enqueue = Mock(return_value=({}, True))
    monkeypatch.setattr("suzent.core.agent_inbox.enqueue_agent_message", enqueue)
    return registry, enqueue


@pytest.mark.parametrize("exit_code,status", [(0, "completed"), (7, "failed")])
async def test_completion_enqueues_once_with_bounded_output(
    commands, monkeypatch, exit_code, status
):
    registry, enqueue = commands
    registry.register("chat", "abc", "Build project", "host")
    monkeypatch.setattr(
        registry,
        "_poll",
        lambda task: {
            "done": True,
            "exit_code": exit_code,
            "output": "x" * 9000,
            "offset": 9000,
        },
    )
    await registry.tick()
    await registry.tick()
    task = registry.get("shell_abc")
    assert task["status"] == status
    assert len(task["result_summary"]) == 8000
    assert task["finished_at"]
    enqueue.assert_called_once()
    payload = enqueue.call_args.kwargs
    assert payload["kind"] == "background_task_result"
    assert payload["target_chat_id"] == "chat"
    assert payload["message_id"] == "shell-result-abc"
    assert f"Exit code: {exit_code}" in payload["content"]


async def test_running_command_does_not_notify_and_keeps_incremental_output(
    commands, monkeypatch
):
    registry, enqueue = commands
    registry.register("chat", "abc", "Build", "host")
    results = iter(
        [
            {"done": False, "output": "first", "offset": 5},
            {"done": True, "exit_code": 0, "output": "last", "offset": 9},
        ]
    )
    offsets = []

    def poll(task):
        offsets.append(task.offset)
        return next(results)

    monkeypatch.setattr(registry, "_poll", poll)
    await registry.tick()
    enqueue.assert_not_called()
    await registry.tick()
    assert offsets == [0, 5]
    assert registry.get("shell_abc")["result_summary"] == "firstlast"


async def test_explicit_read_consumes_completion_without_wakeup(commands):
    registry, enqueue = commands
    registry.register("chat", "abc", "Build", "host")
    registry.observe(
        "chat", "abc", {"done": True, "exit_code": 0, "output": "done"}, consumed=True
    )
    await registry.tick()
    enqueue.assert_not_called()
    assert registry.suppress_wakeup("shell_abc")


async def test_cancel_wins_over_in_flight_poll(commands):
    registry, enqueue = commands
    registry.register("chat", "abc", "Build", "host")
    registry.cancel("other-chat", "abc")
    assert registry.get("shell_abc")["status"] == "running"
    registry.cancel("chat", "abc")
    registry.observe("chat", "abc", {"done": True, "exit_code": -15})
    await registry.tick()
    assert registry.get("shell_abc")["status"] == "cancelled"
    enqueue.assert_not_called()


async def test_failed_enqueue_retries_same_durable_id(commands, monkeypatch):
    registry, enqueue = commands
    registry.register("chat", "abc", "Build", "host")
    registry.observe("chat", "abc", {"done": True, "exit_code": 0})
    enqueue.side_effect = [RuntimeError("busy"), ({}, True)]
    await registry.tick()
    await registry.tick()
    await registry.tick()
    assert enqueue.call_count == 2
    assert (
        enqueue.call_args_list[0].kwargs["message_id"]
        == enqueue.call_args_list[1].kwargs["message_id"]
    )


async def test_sandbox_uses_owning_manager_for_poll_and_stop(commands):
    registry, enqueue = commands
    manager = SimpleNamespace(
        poll_process=Mock(
            return_value={"done": False, "output": "working", "offset": 7}
        ),
        kill_process=Mock(return_value=True),
    )
    registry.register("chat", "abc", "Build", "sandbox", manager=manager)
    await registry.tick()
    manager.poll_process.assert_called_once_with("chat", "abc", 0)
    assert await registry.stop_command("shell_abc")
    manager.kill_process.assert_called_once_with("chat", "abc")
    await registry.tick()
    enqueue.assert_not_called()


async def test_host_process_finishes_after_start_and_notifies(commands, tmp_path):
    from suzent.tools.shell.host_process_registry import HostProcessRegistry

    registry, enqueue = commands
    host = HostProcessRegistry()
    process_id = host.start(
        "bg-test",
        [sys.executable, "-c", "print('finished')"],
        str(tmp_path),
        dict(os.environ),
    )
    registry.register("bg-test", process_id, "Print result", "host")
    try:
        async with asyncio.timeout(5):
            while not enqueue.called:
                await registry.tick()
                await asyncio.sleep(0.01)
        assert registry.get(f"shell_{process_id}")["result_summary"] == "finished\n"
        assert registry.get(f"shell_{process_id}")["exit_code"] == 0
    finally:
        host.evict_chat("bg-test")


def test_removed_chat_is_no_longer_monitored(commands):
    registry, enqueue = commands
    registry.register("chat", "abc", "Build", "host")
    registry.register("other", "def", "Other build", "host")
    registry.remove_chat("chat")
    assert registry.list_tasks("chat") == []
    assert len(registry.list_tasks("other")) == 1
    registry._notify_finished()
    enqueue.assert_not_called()


async def test_failed_stop_keeps_task_running_and_can_notify_later(commands):
    registry, enqueue = commands
    manager = SimpleNamespace(kill_process=Mock(side_effect=RuntimeError("offline")))
    registry.register("chat", "abc", "Build", "sandbox", manager=manager)
    assert not await registry.stop_command("shell_abc")
    assert registry.get("shell_abc")["status"] == "running"
    assert not registry.suppress_wakeup("shell_abc")
    registry.observe("chat", "abc", {"done": True, "exit_code": 0})
    await registry.tick()
    enqueue.assert_called_once()


async def test_queued_completion_is_suppressed_if_agent_already_read_it(
    commands, monkeypatch
):
    from suzent.core.agent_inbox import AgentInboxDispatcher

    registry, enqueue = commands
    registry.register("chat", "abc", "Build", "host")
    registry.observe("chat", "abc", {"done": True, "exit_code": 0})
    await registry.tick()
    message = {**enqueue.call_args.kwargs, "attempts": 1}
    registry.observe("chat", "abc", {"done": True, "exit_code": 0}, consumed=True)
    acknowledge = Mock(return_value=True)
    monkeypatch.setattr(
        "suzent.core.background_commands.get_background_commands", lambda: registry
    )
    monkeypatch.setattr(
        "suzent.core.agent_inbox.get_database",
        lambda: SimpleNamespace(
            get_chat=lambda _: SimpleNamespace(messages=[]),
            acknowledge_agent_message=acknowledge,
        ),
    )
    dispatcher = AgentInboxDispatcher()

    async def unexpected_delivery(message):
        pytest.fail("Consumed command should not wake the agent")

    monkeypatch.setattr(dispatcher, "_deliver", unexpected_delivery)
    await dispatcher._deliver_claimed(message)
    acknowledge.assert_called_once()


@pytest.mark.parametrize("mode", ["host", "sandbox"])
def test_shell_launch_registers_command_for_monitoring(
    commands, monkeypatch, tmp_path, mode
):
    from suzent.tools.shell.bash_tool import ShellCommandBackend
    from suzent.tools.shell.host_process_registry import HostProcessRegistry

    registry, _ = commands
    monkeypatch.setattr(
        "suzent.core.background_commands.get_background_commands", lambda: registry
    )
    monkeypatch.setattr(HostProcessRegistry, "start", lambda *args, **kwargs: "abc")
    tool = ShellCommandBackend()
    tool.chat_id = "chat"
    tool.workspace_root = str(tmp_path)
    tool._manager = SimpleNamespace(start_background=Mock(return_value="abc"))
    result = (
        tool._execute_background_on_host if mode == "host" else tool._execute_background
    )("echo ok", description="Print result")
    assert result.success
    assert registry.get("shell_abc")["mode"] == mode
    assert registry.get("shell_abc")["description"] == "Print result"
