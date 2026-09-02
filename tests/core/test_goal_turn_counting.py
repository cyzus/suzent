"""Goal budget is charged by turns the user took, not by prompt assembly.

The increment used to live inside `plan_reminder_hook`, which runs on every path
that assembles a reminder. Heartbeats, approval resumes, tool continuations and
retries all consumed budget, so `turns_elapsed` measured how often a prompt was
built rather than how much work the user asked for.
"""

from types import SimpleNamespace

import pytest

from suzent.tools.plan_hooks import advance_goal_turn, plan_reminder_hook


class _Goal:
    def __init__(
        self, status: str = "active", turns: int = 0, max_turns: int | None = 10
    ):
        self.id = "goal-1"
        self.status = status
        self.turns_elapsed = turns
        self.max_turns = max_turns
        self.objective = "Ship it"
        self.subgoals: list[str] = []


class _DB:
    def __init__(self, goal: _Goal | None = None, project_id: str | None = "proj-1"):
        self.goal = goal
        self._project_id = project_id
        self.updates: list[tuple[str, int]] = []

    def get_chat_project_id(self, chat_id: str):
        return self._project_id

    def get_goal(self, project_id: str, chat_id: str | None = None):
        return self.goal

    def update_goal(self, goal_id: str, turns_elapsed: int):
        self.updates.append((goal_id, turns_elapsed))
        if self.goal:
            self.goal.turns_elapsed = turns_elapsed

    def list_tasks(self, **kwargs):
        return []


@pytest.fixture
def db(monkeypatch):
    instance = _DB(_Goal())
    monkeypatch.setattr("suzent.tools.plan_hooks.get_database", lambda: instance)
    return instance


# --- the reminder is a pure read --------------------------------------------


@pytest.mark.asyncio
async def test_building_the_reminder_does_not_spend_budget(db):
    await plan_reminder_hook("chat-1", SimpleNamespace())

    assert db.updates == [], "assembling a prompt is a read"


@pytest.mark.asyncio
async def test_repeated_reminders_never_accumulate(db):
    """A heartbeat, an approval resume and a retry each build a reminder."""
    for _ in range(5):
        await plan_reminder_hook("chat-1", SimpleNamespace())

    assert db.goal.turns_elapsed == 0


@pytest.mark.asyncio
async def test_the_reminder_still_reports_the_budget(db):
    db.goal.turns_elapsed = 3
    text = await plan_reminder_hook("chat-1", SimpleNamespace())

    assert "3/10 turns used" in text


# --- the lifecycle event is what charges ------------------------------------


def test_a_completed_turn_charges_one(db):
    advance_goal_turn("chat-1")

    assert db.updates == [("goal-1", 1)]


def test_charging_is_one_per_call(db):
    advance_goal_turn("chat-1")
    advance_goal_turn("chat-1")

    assert db.goal.turns_elapsed == 2


def test_a_paused_goal_is_not_charged(db):
    db.goal.status = "paused"

    advance_goal_turn("chat-1")

    assert db.updates == []


def test_no_goal_is_harmless(monkeypatch):
    instance = _DB(goal=None)
    monkeypatch.setattr("suzent.tools.plan_hooks.get_database", lambda: instance)

    advance_goal_turn("chat-1")

    assert instance.updates == []


def test_no_project_is_harmless(monkeypatch):
    instance = _DB(_Goal(), project_id=None)
    monkeypatch.setattr("suzent.tools.plan_hooks.get_database", lambda: instance)

    advance_goal_turn("chat-1")

    assert instance.updates == []


def test_a_database_failure_does_not_break_the_turn(monkeypatch):
    """Bookkeeping must not be able to fail a turn that already succeeded."""

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("suzent.tools.plan_hooks.get_database", boom)

    advance_goal_turn("chat-1")  # must not raise


# --- which turns qualify ----------------------------------------------------


def test_a_plain_user_turn_is_chargeable_by_default() -> None:
    """process_turn computes `_turn_message` as non-empty only for a real user
    message that is not a heartbeat and not an approval resume; with no explicit
    answer, that is what decides."""
    import inspect

    from suzent.core import chat_processor

    source = inspect.getsource(chat_processor.ChatProcessor.process_turn)

    assert "bool(_turn_message)" in source
    assert "if counts_toward_goal is None" in source


def test_an_autonomous_goal_step_is_chargeable() -> None:
    """It has no user message, but it is a turn of work on the goal. Without
    this, max_turns can never stop a goal whose judge keeps asking for more."""
    import inspect

    from suzent.core import goals

    source = inspect.getsource(goals.run_goal_step)

    assert "counts_toward_goal=True" in source


def test_a_replayed_retry_is_not_chargeable() -> None:
    """The original turn already charged, and apply_retry_checkpoint restores
    chat state, messages and files but not the counter."""
    import inspect

    from suzent.core import chat_processor

    source = inspect.getsource(chat_processor.ChatProcessor._handle_retry_command)

    assert "counts_toward_goal=False" in source


def test_an_explicit_answer_overrides_the_inference() -> None:
    """The two callers that know better must be able to say so."""
    import inspect

    from suzent.core import chat_processor

    signature = inspect.signature(chat_processor.ChatProcessor.process_turn)

    assert signature.parameters["counts_toward_goal"].default is None
