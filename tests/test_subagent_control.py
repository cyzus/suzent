"""Steering and stopping sub-agents from their parent chat."""

import pytest

from suzent.core import subagent_runner
from suzent.core.stream_registry import StreamControl, stream_controls


@pytest.fixture
def isolated_tasks(monkeypatch):
    """A clean task registry whose terminal writes do not touch the database."""
    tasks: dict = {}
    monkeypatch.setattr(subagent_runner, "_tasks", tasks)
    monkeypatch.setattr(subagent_runner, "_broadcast_task_update", lambda task: None)
    monkeypatch.setattr(subagent_runner, "_persist_task_state", lambda task: None)
    return tasks


def _task(task_id: str, parent: str, status: str = "running") -> None:
    return subagent_runner.SubAgentTask(
        task_id=task_id,
        parent_chat_id=parent,
        description="work",
        tools_allowed=[],
        status=status,
        chat_id=f"chat-{task_id}",
    )


@pytest.fixture
def live_control():
    """A control registered for a child chat, cleaned up after the test."""
    registered: list[str] = []

    def register(chat_id: str) -> StreamControl:
        control = StreamControl()
        stream_controls[chat_id] = control
        registered.append(chat_id)
        return control

    yield register
    for chat_id in registered:
        stream_controls.pop(chat_id, None)


# ─── steer ───────────────────────────────────────────────────────────────────


async def test_steer_injects_into_the_childs_live_run(isolated_tasks, live_control):
    isolated_tasks["t1"] = _task("t1", "parent-1")
    control = live_control("chat-t1")
    seen: list[str] = []
    control.inject = lambda content: (seen.append(content), "enq-1")[1]

    assert await subagent_runner.steer_subagent("t1", "use ripgrep instead") == "enq-1"
    assert seen == ["[User interrupted to redirect]: use ripgrep instead"]


async def test_steer_leaves_the_child_running(isolated_tasks, live_control):
    """The point of injecting rather than steering: nothing is torn down."""
    isolated_tasks["t1"] = _task("t1", "parent-1")
    control = live_control("chat-t1")
    control.inject = lambda content: "enq-1"

    await subagent_runner.steer_subagent("t1", "go on")

    assert isolated_tasks["t1"].status == "running"
    assert not control.cancel_event.is_set()


async def test_steer_reports_when_the_run_cannot_take_a_message(
    isolated_tasks, live_control
):
    isolated_tasks["t1"] = _task("t1", "parent-1")
    control = live_control("chat-t1")
    control.inject = lambda content: None  # between runs

    assert await subagent_runner.steer_subagent("t1", "hi") is None


async def test_steer_refuses_a_child_with_no_live_run(isolated_tasks):
    isolated_tasks["t1"] = _task("t1", "parent-1")
    assert await subagent_runner.steer_subagent("t1", "hi") is None


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_steer_refuses_a_finished_child(isolated_tasks, status):
    isolated_tasks["t1"] = _task("t1", "parent-1", status=status)
    assert await subagent_runner.steer_subagent("t1", "hi") is None


async def test_steer_refuses_an_unknown_child(isolated_tasks):
    assert await subagent_runner.steer_subagent("nope", "hi") is None


# ─── stop cascade ────────────────────────────────────────────────────────────


async def test_stop_reaches_every_child_of_that_parent(isolated_tasks):
    isolated_tasks["t1"] = _task("t1", "parent-1")
    isolated_tasks["t2"] = _task("t2", "parent-1", status="queued")

    stopped = await subagent_runner.stop_subagents_for_parent("parent-1")

    assert sorted(stopped) == ["t1", "t2"]
    assert isolated_tasks["t1"].status == "cancelled"
    assert isolated_tasks["t2"].status == "cancelled"


async def test_stopped_children_say_the_user_did_it(isolated_tasks):
    """Not the generic 'the run was cancelled' a collateral kill used to leave."""
    isolated_tasks["t1"] = _task("t1", "parent-1")

    await subagent_runner.stop_subagents_for_parent("parent-1")

    assert isolated_tasks["t1"].error == "Stopped by you"


async def test_stop_spares_another_chats_children(isolated_tasks):
    isolated_tasks["mine"] = _task("mine", "parent-1")
    isolated_tasks["theirs"] = _task("theirs", "parent-2")

    stopped = await subagent_runner.stop_subagents_for_parent("parent-1")

    assert stopped == ["mine"]
    assert isolated_tasks["theirs"].status == "running"


async def test_stop_skips_children_that_already_finished(isolated_tasks):
    isolated_tasks["done"] = _task("done", "parent-1", status="completed")

    assert await subagent_runner.stop_subagents_for_parent("parent-1") == []
    assert isolated_tasks["done"].status == "completed"


async def test_stop_on_a_chat_with_no_children_is_quiet(isolated_tasks):
    assert await subagent_runner.stop_subagents_for_parent("parent-1") == []
    assert await subagent_runner.stop_subagents_for_parent("") == []


# ─── the stop notice survives the display rebuild ────────────────────────────


def _notice(text: str) -> dict:
    return {"role": "notice", "content": text}


def test_rebuild_keeps_a_trailing_notice():
    """A notice has no counterpart in agent history, so the rebuild drops it."""
    from suzent.core.chat_processor import _preserve_trailing_notices

    existing = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "working"},
        _notice("⏹ Also stopped 2 sub-agent(s)"),
    ]
    rebuilt = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "working"},
    ]

    assert _preserve_trailing_notices(rebuilt, existing) == [*rebuilt, existing[-1]]


def test_rebuild_keeps_several_trailing_notices_in_order():
    from suzent.core.chat_processor import _preserve_trailing_notices

    existing = [{"role": "user", "content": "go"}, _notice("first"), _notice("second")]

    kept = _preserve_trailing_notices([{"role": "user", "content": "go"}], existing)

    assert [row["content"] for row in kept[1:]] == ["first", "second"]


def test_rebuild_leaves_a_mid_log_notice_alone():
    """Re-appending it would walk it further down the log on every turn."""
    from suzent.core.chat_processor import _preserve_trailing_notices

    existing = [_notice("old"), {"role": "user", "content": "go"}]
    rebuilt = [{"role": "user", "content": "go"}]

    assert _preserve_trailing_notices(rebuilt, existing) == rebuilt


def test_rebuild_is_unchanged_when_there_is_nothing_to_keep():
    from suzent.core.chat_processor import _preserve_trailing_notices

    rebuilt = [{"role": "user", "content": "go"}]

    assert _preserve_trailing_notices(rebuilt, []) == rebuilt
    assert _preserve_trailing_notices(rebuilt, None) == rebuilt
