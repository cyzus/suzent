"""A sub-agent whose model stalls keeps working instead of failing.

The model call going quiet is usually the provider still generating (a large
tool argument is buffered until complete), so the turn is resumed. A parent
that was blocked on the child gets its turn back and is woken at the end.
"""

import asyncio

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

import suzent.core.subagent_runner as subagent_runner
from suzent.core.chat_processor import ChatProcessor, ModelStalledError
from suzent.core.stream_parser import ErrorEvent, StreamParser
from suzent.streaming import MODEL_STALLED_CODE, model_failure_code


@pytest.fixture
def runner_env(temp_db, monkeypatch: pytest.MonkeyPatch):
    temp_db.create_chat("Parent", {}, chat_id="parent-1")
    monkeypatch.setattr(subagent_runner, "get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    monkeypatch.setattr(subagent_runner, "_STALL_RETRY_DELAY_SECONDS", 0)

    async def no_notify(*args, **kwargs) -> None:
        return None

    woken: list[str] = []
    monkeypatch.setattr(subagent_runner, "_notify_parent", no_notify)
    monkeypatch.setattr(
        subagent_runner, "_queue_parent_wakeup", lambda task: woken.append(task.task_id)
    )
    monkeypatch.setattr(
        "suzent.core.providers.get_default_chat_model", lambda: "anthropic/claude-x"
    )
    yield woken
    subagent_runner._tasks.clear()


def _script_turns(monkeypatch: pytest.MonkeyPatch, outcomes: list) -> list[dict]:
    """Make each process_turn_text call take the next outcome in order."""
    calls: list[dict] = []

    async def fake_turn(self, **kwargs) -> str:
        calls.append(kwargs)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, asyncio.Event):
            await outcome.wait()
            return "done"
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(ChatProcessor, "process_turn_text", fake_turn)
    return calls


def test_a_quiet_or_dropped_model_call_counts_as_a_stall() -> None:
    assert model_failure_code(TimeoutError("no event for 120s")) == MODEL_STALLED_CODE
    assert (
        model_failure_code(ModelAPIError("m", "Server disconnected"))
        == MODEL_STALLED_CODE
    )
    assert model_failure_code(ModelHTTPError(400, "m", "bad request")) is None
    assert model_failure_code(ValueError("bug")) is None


def test_the_stall_code_survives_the_stream() -> None:
    chunk = (
        'data: {"type":"RUN_ERROR","message":"Timed out","code":"model_stalled"}\n\n'
    )

    events = [e for e in StreamParser().parse([chunk]) if isinstance(e, ErrorEvent)]

    assert events == [ErrorEvent("Timed out", MODEL_STALLED_CODE)]


async def test_a_stalled_subagent_resumes_instead_of_failing(
    runner_env, monkeypatch
) -> None:
    calls = _script_turns(
        monkeypatch, [ModelStalledError("Timed out"), "Rebuilt the slides."]
    )

    task = await subagent_runner.spawn_subagent(
        parent_chat_id="parent-1",
        description="Rebuild the slides",
        tools_allowed=[],
        run_in_background=True,
    )
    await task.runner_task

    assert task.status == "completed"
    assert task.error is None
    assert len(calls) == 2
    assert calls[0]["message_content"] == "Rebuild the slides"
    # The resume is a hidden reminder, not words put in the user's mouth.
    assert calls[1]["message_content"] == ""
    assert "cut off" in calls[1]["system_reminders"][0]


async def test_a_subagent_that_keeps_stalling_fails_in_the_end(
    runner_env, monkeypatch
) -> None:
    stalls = subagent_runner.SUBAGENT_STALL_RETRIES + 1
    calls = _script_turns(
        monkeypatch, [ModelStalledError("Timed out") for _ in range(stalls)]
    )

    task = await subagent_runner.spawn_subagent(
        parent_chat_id="parent-1",
        description="Rebuild the slides",
        tools_allowed=[],
        run_in_background=True,
    )
    await task.runner_task

    assert task.status == "failed"
    assert len(calls) == stalls


async def test_a_blocking_subagent_moves_to_the_background_when_it_stalls(
    runner_env, monkeypatch
) -> None:
    woken = runner_env
    still_working = asyncio.Event()
    _script_turns(monkeypatch, [ModelStalledError("Timed out"), still_working])

    task = await asyncio.wait_for(
        subagent_runner.spawn_subagent(
            parent_chat_id="parent-1",
            description="Rebuild the slides",
            tools_allowed=[],
            run_in_background=False,
        ),
        timeout=5,
    )

    # The parent has its turn back while the child is still going.
    assert task.backgrounded
    assert task.status == "running"
    assert woken == []

    still_working.set()
    await task.runner_task

    assert task.status == "completed"
    # Having let go of the parent, the child wakes it like a background run.
    assert woken == [task.task_id]


async def test_a_blocking_subagent_that_never_stalls_still_blocks(
    runner_env, monkeypatch
) -> None:
    woken = runner_env
    _script_turns(monkeypatch, ["Rebuilt the slides."])

    task = await subagent_runner.spawn_subagent(
        parent_chat_id="parent-1",
        description="Rebuild the slides",
        tools_allowed=[],
        run_in_background=False,
    )

    assert task.status == "completed"
    assert not task.backgrounded
    assert woken == []


async def test_stopping_the_parent_stops_a_child_it_still_waits_on(
    runner_env, monkeypatch
) -> None:
    never = asyncio.Event()
    _script_turns(monkeypatch, [never])

    waiting = asyncio.create_task(
        subagent_runner.spawn_subagent(
            parent_chat_id="parent-1",
            description="Rebuild the slides",
            tools_allowed=[],
            run_in_background=False,
        )
    )
    for _ in range(50):
        await asyncio.sleep(0)
        tasks = list(subagent_runner._tasks.values())
        if tasks and tasks[0].runner_task is not None:
            break
    child = tasks[0]

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    with pytest.raises(asyncio.CancelledError):
        await child.runner_task

    assert child.status == "cancelled"
