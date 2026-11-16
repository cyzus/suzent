"""Unit tests for goal-mode pure logic (no DB / no network)."""

import asyncio
from types import SimpleNamespace

from suzent.core.goals import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PAUSED,
    _budget_exhausted,
    _build_continuation_reminder,
    _build_judge_user_prompt,
    _parse_verdict,
    format_status,
    judge_goal,
    maybe_continue_goal,
    summarize_turn_evidence,
)


def _goal(**kw):
    """Build a GoalModel-like stub for the pure display/budget helpers."""
    defaults = dict(
        id=1,
        objective="do a thing",
        status=STATUS_ACTIVE,
        turns_elapsed=0,
        max_turns=20,
        subgoals=[],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# ─── _parse_verdict ──────────────────────────────────────────────────────────


def test_parse_verdict_done_true():
    assert _parse_verdict('{"done": true, "reason": "all tests pass"}') == (
        True,
        "all tests pass",
    )


def test_parse_verdict_done_false():
    assert _parse_verdict('{"done": false, "reason": "still failing"}') == (
        False,
        "still failing",
    )


def test_parse_verdict_extracts_json_from_prose():
    raw = 'Sure! Here is my verdict:\n{"done": true, "reason": "shipped"} \nThanks'
    assert _parse_verdict(raw) == (True, "shipped")


def test_parse_verdict_string_boolean():
    assert _parse_verdict('{"done": "yes", "reason": "ok"}') == (True, "ok")
    assert _parse_verdict('{"done": "no", "reason": "nope"}') == (False, "nope")


def test_parse_verdict_missing_done_key():
    assert _parse_verdict('{"reason": "no verdict"}') is None


def test_parse_verdict_empty():
    assert _parse_verdict("") is None
    assert _parse_verdict("   ") is None


def test_parse_verdict_garbage():
    assert _parse_verdict("not json at all") is None


# ─── _budget_exhausted ───────────────────────────────────────────────────────


def test_budget_exhausted_true_when_at_limit():
    assert _budget_exhausted(_goal(turns_elapsed=20, max_turns=20)) is True
    assert _budget_exhausted(_goal(turns_elapsed=21, max_turns=20)) is True


def test_budget_not_exhausted_below_limit():
    assert _budget_exhausted(_goal(turns_elapsed=5, max_turns=20)) is False


def test_budget_never_exhausted_without_max_turns():
    assert _budget_exhausted(_goal(turns_elapsed=999, max_turns=None)) is False


# ─── format_status ───────────────────────────────────────────────────────────


def test_format_status_none():
    assert "No active goal" in format_status(None)


def test_format_status_completed_and_cancelled_read_as_no_goal():
    assert "No active goal" in format_status(_goal(status=STATUS_COMPLETED))
    assert "No active goal" in format_status(_goal(status=STATUS_CANCELLED))


def test_format_status_active_with_subgoals():
    out = format_status(
        _goal(
            objective="fix lints",
            status=STATUS_ACTIVE,
            turns_elapsed=2,
            max_turns=10,
            subgoals=["ruff clean", "mypy clean"],
        )
    )
    assert "2/10" in out
    assert "fix lints" in out
    assert "ruff clean" in out
    assert "mypy clean" in out


def test_format_status_paused_icon():
    assert "⏸" in format_status(
        _goal(status=STATUS_PAUSED, turns_elapsed=20, max_turns=20)
    )


# ─── judge prompt builder ────────────────────────────────────────────────────


def test_judge_prompt_includes_subgoals():
    prompt = _build_judge_user_prompt("main goal", ["sub a", "sub b"], "the response")
    assert "main goal" in prompt
    assert "1. sub a" in prompt
    assert "2. sub b" in prompt
    assert "the response" in prompt


def test_judge_prompt_truncates_long_response():
    prompt = _build_judge_user_prompt("g", [], "x" * 9000)
    # Response is capped at 4000 chars in the prompt body.
    assert "x" * 4001 not in prompt


# ─── judge_goal fail-open semantics ──────────────────────────────────────────


def _patch_judge(monkeypatch, model, complete_impl):
    class _Router:
        def get_model_id(self, role):
            assert role == "goal_judge"
            return model

    class _Client:
        def __init__(self, model=None):
            pass

        async def complete(self, **kwargs):
            return await complete_impl(**kwargs)

    monkeypatch.setattr("suzent.core.role_router.get_role_router", lambda: _Router())
    monkeypatch.setattr("suzent.llm.LLMClient", _Client)


def test_judge_goal_no_model_fails_open(monkeypatch):
    async def _never(**kwargs):  # pragma: no cover - should not be called
        raise AssertionError("complete should not be called without a model")

    _patch_judge(monkeypatch, None, _never)
    verdict, _reason, parse_failed = asyncio.run(judge_goal("g", [], "r"))
    assert verdict == "continue"
    assert parse_failed is True


def test_judge_goal_transport_error_fails_open(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("network down")

    _patch_judge(monkeypatch, "cheap/model", _boom)
    verdict, _reason, parse_failed = asyncio.run(judge_goal("g", [], "r"))
    assert verdict == "continue"
    # Transport errors must NOT count as parse failures (no auto-pause).
    assert parse_failed is False


def test_judge_goal_unparseable_marks_parse_failed(monkeypatch):
    async def _garbage(**kwargs):
        return "I cannot decide"

    _patch_judge(monkeypatch, "cheap/model", _garbage)
    verdict, _reason, parse_failed = asyncio.run(judge_goal("g", [], "r"))
    assert verdict == "continue"
    assert parse_failed is True


def test_judge_goal_done(monkeypatch):
    async def _done(**kwargs):
        return '{"done": true, "reason": "complete"}'

    _patch_judge(monkeypatch, "cheap/model", _done)
    verdict, reason, parse_failed = asyncio.run(judge_goal("g", [], "r"))
    assert verdict == "done"
    assert reason == "complete"
    assert parse_failed is False


# ─── Evidence extraction & deterministic ZCode-style gates ───────────────────


def test_summarize_turn_evidence_flags_unverified_edits():
    msg = {
        "parts": [
            {
                "type": "tool",
                "toolName": "run_command",
                "args": '{"content": "pytest"}',
                "state": "completed",
                "output": "1 failed [exit code: 1]",
            },
            {
                "type": "tool",
                "toolName": "edit_file",
                "args": '{"file_path": "src/app.py"}',
                "state": "completed",
                "output": "Replaced 1 occurrence",
            },
        ]
    }
    evidence = summarize_turn_evidence(msg)
    assert "edit_file" in evidence
    assert "STATUS: UNVERIFIED_EDITS" in evidence


def test_summarize_turn_evidence_clears_when_verified_after_edit():
    msg = {
        "parts": [
            {
                "type": "tool",
                "toolName": "edit_file",
                "args": '{"file_path": "src/app.py"}',
                "state": "completed",
                "output": "Replaced 1 occurrence",
            },
            {
                "type": "tool",
                "toolName": "run_command",
                "args": '{"content": "pytest"}',
                "state": "completed",
                "output": "2 passed [exit code: 0]",
            },
        ]
    }
    evidence = summarize_turn_evidence(msg)
    assert "STATUS: UNVERIFIED_EDITS" not in evidence
    assert "STATUS: LAST_COMMAND_FAILED" not in evidence
    assert "[OK]" in evidence


def test_summarize_turn_evidence_flags_failed_command():
    msg = {
        "parts": [
            {
                "type": "tool",
                "toolName": "edit_file",
                "args": '{"file_path": "src/app.py"}',
                "state": "completed",
                "output": "Replaced 1 occurrence",
            },
            {
                "type": "tool",
                "toolName": "run_command",
                "args": '{"content": "pytest"}',
                "state": "completed",
                "output": "AssertionError [exit code: 1]",
            },
        ]
    }
    evidence = summarize_turn_evidence(msg)
    assert "STATUS: LAST_COMMAND_FAILED" in evidence


def test_maybe_continue_goal_blocks_completion_when_open_tasks_remain(monkeypatch):
    goal = _goal(turns_elapsed=1, max_turns=10)
    step_calls = []

    class _FakeDB:
        def get_chat_project_id(self, chat_id):
            return "proj-1"

        def get_goal(self, project_id, chat_id=None):
            return goal

        def list_tasks(self, **kwargs):
            return [
                SimpleNamespace(id=3, title="Write unit tests", status="in_progress")
            ]

    async def _never_judge(*args, **kwargs):
        raise AssertionError("judge LLM must not be called while open tasks remain")

    async def _fake_step(chat_id, user_id, judge_feedback=""):
        step_calls.append((chat_id, user_id, judge_feedback))

    monkeypatch.setattr("suzent.core.goals.get_database", lambda: _FakeDB())
    monkeypatch.setattr("suzent.core.goals.judge_goal", _never_judge)
    monkeypatch.setattr("suzent.core.goals.run_goal_step", _fake_step)

    asyncio.run(maybe_continue_goal("chat-1", "u1", "All done!", False))
    assert len(step_calls) == 1
    assert "[#3] Write unit tests" in step_calls[0][2]


def test_maybe_continue_goal_blocks_completion_on_unverified_edits(monkeypatch):
    goal = _goal(turns_elapsed=1, max_turns=10)
    step_calls = []

    class _FakeDB:
        def get_chat_project_id(self, chat_id):
            return "proj-1"

        def get_goal(self, project_id, chat_id=None):
            return goal

        def list_tasks(self, **kwargs):
            return []

    async def _never_judge(*args, **kwargs):
        raise AssertionError("judge LLM must not be called when edits are unverified")

    async def _fake_step(chat_id, user_id, judge_feedback=""):
        step_calls.append((chat_id, user_id, judge_feedback))

    monkeypatch.setattr("suzent.core.goals.get_database", lambda: _FakeDB())
    monkeypatch.setattr("suzent.core.goals.judge_goal", _never_judge)
    monkeypatch.setattr("suzent.core.goals.run_goal_step", _fake_step)

    unverified_msg = {
        "parts": [
            {
                "type": "tool",
                "toolName": "write_file",
                "args": '{"file_path": "main.py"}',
                "state": "completed",
                "output": "Wrote file",
            }
        ]
    }
    asyncio.run(
        maybe_continue_goal(
            "chat-1", "u1", "I finished the implementation.", False, unverified_msg
        )
    )
    assert len(step_calls) == 1
    assert "verification command" in step_calls[0][2]


def test_maybe_continue_goal_passes_judge_reason_to_next_step(monkeypatch):
    goal = _goal(turns_elapsed=1, max_turns=10)
    step_calls = []

    class _FakeDB:
        def get_chat_project_id(self, chat_id):
            return "proj-1"

        def get_goal(self, project_id, chat_id=None):
            return goal

        def list_tasks(self, **kwargs):
            return []

    async def _fake_judge(objective, subgoals, last_response, evidence=""):
        assert "pytest" in evidence
        return "continue", "Edge case for empty input not tested yet", False

    async def _fake_step(chat_id, user_id, judge_feedback=""):
        step_calls.append(judge_feedback)

    monkeypatch.setattr("suzent.core.goals.get_database", lambda: _FakeDB())
    monkeypatch.setattr("suzent.core.goals.judge_goal", _fake_judge)
    monkeypatch.setattr("suzent.core.goals.run_goal_step", _fake_step)

    verified_msg = {
        "parts": [
            {
                "type": "tool",
                "toolName": "run_command",
                "args": '{"content": "pytest"}',
                "state": "completed",
                "output": "1 passed [exit code: 0]",
            }
        ]
    }
    asyncio.run(maybe_continue_goal("chat-1", "u1", "Ran 1 test.", False, verified_msg))
    assert step_calls == ["Edge case for empty input not tested yet"]
    assert "Edge case for empty input not tested yet" in _build_continuation_reminder(
        step_calls[0]
    )
