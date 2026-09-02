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


def test_chargeability_is_its_own_predicate_not_the_hook_one() -> None:
    """`_turn_message` answers 'should retrieval hooks run', which needs query
    text. Chargeability answers 'did the user ask for work', which a file alone
    does — an attachment-only prompt runs the agent and can trigger
    continuation, so it must spend a slot. Reusing the first for the second let
    those turns run free."""
    import inspect

    from suzent.core import chat_processor

    source = inspect.getsource(chat_processor.ChatProcessor.process_turn)

    assert "_is_user_turn = bool(" in source
    assert "or files" in source
    assert "if counts_toward_goal is None" in source


def test_the_budget_is_charged_before_continuation_is_scheduled() -> None:
    """Charging inside the background post-process raced the continuation
    scheduler: the judge could read the previous count, start one more
    autonomous run, and take the goal past max_turns."""
    import inspect

    from suzent.core import chat_processor

    source = inspect.getsource(chat_processor.ChatProcessor.process_turn)
    charge = source.index("advance_goal_turn(chat_id, only_goal_id=")
    schedule = source.index("maybe_continue_goal")

    assert charge < schedule, "the increment must land before the judge looks"


def test_post_processing_no_longer_charges() -> None:
    """One place only, or the two can disagree."""
    import inspect

    from suzent.core import chat_processor

    source = inspect.getsource(chat_processor.ChatProcessor._post_process_turn)

    assert "advance_goal_turn" not in source


def test_an_autonomous_goal_step_is_chargeable() -> None:
    """It has no user message, but it is a turn of work on the goal. Without
    this, max_turns can never stop a goal whose judge keeps asking for more."""
    import inspect

    from suzent.core import goals

    source = inspect.getsource(goals.run_goal_step)

    assert "counts_toward_goal=True" in source


def test_a_retry_is_charged_like_any_other_turn() -> None:
    """A retry does real work, and the checkpoint is written at turn start —
    before the outcome is known — so nothing records whether the first attempt
    was charged. Forcing it uncharged let a retry of a *failed* turn go
    uncounted and a goal run past max_turns. For a budget whose job is to stop
    runaway work, pausing early is recoverable and failing to stop is not."""
    import inspect

    from suzent.core import chat_processor

    source = inspect.getsource(chat_processor.ChatProcessor._handle_retry_command)

    assert "counts_toward_goal=False" not in source


def test_the_flag_reaches_process_turn_through_every_entry_point() -> None:
    """run_goal_step goes through process_background_turn -> process_turn_text
    -> process_turn. A gap anywhere raises TypeError, which run_goal_step
    catches and only logs — so autonomous steps would stop silently."""
    import inspect

    from suzent.core.chat_processor import ChatProcessor

    for method in ("process_turn", "process_turn_text", "process_background_turn"):
        params = inspect.signature(getattr(ChatProcessor, method)).parameters
        assert "counts_toward_goal" in params, method


def test_an_explicit_answer_overrides_the_inference() -> None:
    """The two callers that know better must be able to say so."""
    import inspect

    from suzent.core import chat_processor

    signature = inspect.signature(chat_processor.ChatProcessor.process_turn)

    assert signature.parameters["counts_toward_goal"].default is None


def test_a_goal_created_during_the_turn_is_not_charged(db):
    """The turn that sets a goal did not cost that goal anything. Charging it
    pauses a max_turns=1 goal before it runs a single autonomous step."""
    created_mid_turn = _Goal()
    created_mid_turn.id = "goal-new"
    db.goal = created_mid_turn

    advance_goal_turn("chat-1", only_goal_id="goal-that-was-running")

    assert db.updates == []


def test_the_goal_running_at_turn_start_is_charged(db):
    advance_goal_turn("chat-1", only_goal_id="goal-1")

    assert db.updates == [("goal-1", 1)]


def test_active_goal_id_reads_the_current_goal(db):
    from suzent.tools.plan_hooks import active_goal_id

    assert active_goal_id("chat-1") == "goal-1"

    db.goal.status = "paused"
    assert active_goal_id("chat-1") is None


def test_steering_is_charged() -> None:
    """process_steer puts its text straight into history, so message_content is
    empty — but it is user-initiated work that can trigger continuation."""
    import inspect

    from suzent.core import chat_processor

    source = inspect.getsource(chat_processor.ChatProcessor.process_steer)

    assert "counts_toward_goal=True" in source
