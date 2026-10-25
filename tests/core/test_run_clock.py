import pytest

from suzent.core.run_clock import RunClock


def test_clock_excludes_overlapping_human_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    monkeypatch.setattr("suzent.core.run_clock.time.monotonic", lambda: now)
    clock = RunClock()
    now = 10.0
    with clock.paused():
        now = 20.0
        with clock.paused():
            now = 100.0
            assert clock.elapsed() == 10.0
        now = 200.0
    now = 205.0
    assert clock.elapsed() == 15.0


def test_clock_resumes_after_cancelled_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 0.0
    monkeypatch.setattr("suzent.core.run_clock.time.monotonic", lambda: now)
    clock = RunClock()
    now = 2.0
    with pytest.raises(RuntimeError), clock.paused():
        now = 100.0
        raise RuntimeError("cancelled")
    now = 103.0
    assert clock.elapsed() == 5.0


async def test_ask_question_pauses_clock_until_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from types import SimpleNamespace
    from suzent.core.agent_deps import AgentDeps
    from suzent.tools.ask_question_tool import AskQuestionTool, QuestionItem

    now = 0.0
    monkeypatch.setattr("suzent.core.run_clock.time.monotonic", lambda: now)
    future = asyncio.get_running_loop().create_future()
    monkeypatch.setattr(
        "suzent.tools.ask_question_tool.pending_questions.create", lambda *_: future
    )
    deps = AgentDeps(
        chat_id="clock-test", a2ui_queue=asyncio.Queue(), run_clock=RunClock()
    )
    now = 5.0
    task = asyncio.create_task(
        AskQuestionTool().forward(
            SimpleNamespace(deps=deps),
            [QuestionItem(question="Continue?")],
        )
    )
    await deps.a2ui_queue.get()
    now = 3605.0
    assert deps.run_clock.elapsed() == 5.0
    future.set_result({"answer": "yes"})
    await task
    now = 3608.0
    assert deps.run_clock.elapsed() == 8.0
