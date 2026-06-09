"""Unit tests for goal-mode pure logic (no DB / no network)."""

import asyncio

from suzent.core.goals import (
    GoalState,
    STATUS_ACTIVE,
    STATUS_CLEARED,
    STATUS_DONE,
    STATUS_PAUSED,
    _build_continuation_prompt,
    _build_judge_user_prompt,
    _parse_verdict,
    format_status,
    judge_goal,
)


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


# ─── GoalState serialization ────────────────────────────────────────────────


def test_goalstate_roundtrip():
    state = GoalState(
        objective="port feature X",
        status=STATUS_ACTIVE,
        turn=3,
        max_turns=20,
        subgoals=["tests pass", "CI green"],
        parse_failures=1,
    )
    restored = GoalState.from_dict(state.to_dict())
    assert restored == state


def test_goalstate_from_dict_requires_objective():
    assert GoalState.from_dict({"status": "active"}) is None
    assert GoalState.from_dict({}) is None
    assert GoalState.from_dict(None) is None


def test_goalstate_from_dict_defaults():
    state = GoalState.from_dict({"objective": "do a thing"})
    assert state.status == STATUS_ACTIVE
    assert state.turn == 0
    assert state.subgoals == []
    assert state.parse_failures == 0


# ─── format_status ───────────────────────────────────────────────────────────


def test_format_status_none():
    assert "No active goal" in format_status(None)


def test_format_status_cleared():
    state = GoalState(objective="", status=STATUS_CLEARED)
    assert "No active goal" in format_status(state)


def test_format_status_active_with_subgoals():
    state = GoalState(
        objective="fix lints",
        status=STATUS_ACTIVE,
        turn=2,
        max_turns=10,
        subgoals=["ruff clean", "mypy clean"],
    )
    out = format_status(state)
    assert "2/10" in out
    assert "fix lints" in out
    assert "ruff clean" in out
    assert "mypy clean" in out


def test_format_status_done_icon():
    state = GoalState(objective="x", status=STATUS_DONE, turn=5, max_turns=20)
    assert "✓" in format_status(state)


def test_format_status_paused_icon():
    state = GoalState(objective="x", status=STATUS_PAUSED, turn=20, max_turns=20)
    assert "⏸" in format_status(state)


# ─── prompt builders ─────────────────────────────────────────────────────────


def test_judge_prompt_includes_subgoals():
    prompt = _build_judge_user_prompt(
        "main goal", ["sub a", "sub b"], "the response"
    )
    assert "main goal" in prompt
    assert "1. sub a" in prompt
    assert "2. sub b" in prompt
    assert "the response" in prompt


def test_judge_prompt_truncates_long_response():
    prompt = _build_judge_user_prompt("g", [], "x" * 9000)
    # Response is capped at 4000 chars in the prompt body.
    assert "x" * 4001 not in prompt


def test_continuation_prompt_includes_step_and_objective():
    state = GoalState(objective="ship it", turn=4, max_turns=12, subgoals=["a"])
    prompt = _build_continuation_prompt(state)
    assert "step 4/12" in prompt
    assert "ship it" in prompt
    assert "1. a" in prompt


# ─── judge_goal fail-open semantics ──────────────────────────────────────────


def _patch_judge(monkeypatch, model, complete_impl):
    class _Router:
        def get_model_id(self, role):
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
