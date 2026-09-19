"""Scheduled tasks: schedule kinds, catch-up, and chat binding."""

from datetime import datetime, timedelta, timezone

import pytest

from suzent.core import scheduler as scheduler_mod
from suzent.core.scheduler import (
    SchedulerBrain,
    build_bound_task_reminder,
    compute_next_run,
    is_missed_run,
    sync_heartbeat_tasks,
)
from suzent.core.stream_registry import StreamControl, stream_controls


class _Recorder:
    """Stands in for the HeartbeatRunner when a bound task fires."""

    def __init__(self, response: str = "found something"):
        self.response = response
        self.calls: list[dict] = []
        self.pending: list[str] = []
        self.enabled = True

    async def run_bound_turn(
        self,
        chat_id,
        reminder,
        *,
        suppress_ok=False,
        heartbeat_approvals=False,
        persist_to_chat=False,
        **kwargs,
    ):
        self.calls.append(
            {
                "chat_id": chat_id,
                "reminder": reminder,
                "suppress_ok": suppress_ok,
                "heartbeat_approvals": heartbeat_approvals,
                "persist_to_chat": persist_to_chat,
            }
        )
        return self.response

    def mark_heartbeat_pending(self, chat_id):
        self.pending.append(chat_id)


@pytest.fixture
def runner(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr("suzent.core.heartbeat.get_active_heartbeat", lambda: recorder)
    return recorder


# -- schedule kinds --------------------------------------------------------


def test_interval_next_run_is_one_interval_out(temp_db):
    job_id = temp_db.create_cron_job(
        name="poll", prompt="check", schedule_kind="interval", interval_minutes=15
    )
    base = datetime(2026, 1, 1, 9, 0)
    assert compute_next_run(
        temp_db.get_cron_job(job_id), after=base
    ) == base + timedelta(minutes=15)


def test_one_shot_reports_no_further_run_once_it_has_fired(temp_db):
    run_at = datetime.now() + timedelta(hours=1)
    job_id = temp_db.create_cron_job(
        name="remind", prompt="poke", schedule_kind="once", run_at=run_at
    )
    assert compute_next_run(temp_db.get_cron_job(job_id)) == run_at

    temp_db.update_cron_job_run_state(job_id, last_run_at=datetime.now())
    assert compute_next_run(temp_db.get_cron_job(job_id)) is None


def test_cron_honours_the_task_timezone(temp_db):
    """Midnight in Tokyo is a different instant than midnight here."""
    local = temp_db.create_cron_job(name="a", cron_expr="0 0 * * *", prompt="x")
    tokyo = temp_db.create_cron_job(
        name="b", cron_expr="0 0 * * *", prompt="x", timezone="Asia/Tokyo"
    )
    base = datetime(2026, 1, 1, 12, 0)
    assert compute_next_run(
        temp_db.get_cron_job(local), after=base
    ) != compute_next_run(temp_db.get_cron_job(tokyo), after=base)


def test_unknown_timezone_falls_back_to_local_rather_than_failing(temp_db):
    job_id = temp_db.create_cron_job(
        name="c", cron_expr="0 * * * *", prompt="x", timezone="Mars/Olympus"
    )
    assert compute_next_run(temp_db.get_cron_job(job_id)) is not None


def test_jitter_stays_inside_its_window(temp_db):
    job_id = temp_db.create_cron_job(
        name="d",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=10,
        jitter_seconds=60,
    )
    job = temp_db.get_cron_job(job_id)
    base = datetime(2026, 1, 1, 9, 0)
    for _ in range(20):
        nxt = compute_next_run(job, after=base)
        assert (
            base + timedelta(minutes=10)
            <= nxt
            <= base + timedelta(minutes=10, seconds=60)
        )


# -- catch-up --------------------------------------------------------------


def test_a_run_overdue_by_more_than_one_period_counts_as_missed(temp_db):
    job_id = temp_db.create_cron_job(
        name="e", prompt="x", schedule_kind="interval", interval_minutes=10
    )
    now = datetime.now()
    temp_db.update_cron_job_run_state(job_id, next_run_at=now - timedelta(minutes=45))
    assert is_missed_run(temp_db.get_cron_job(job_id), now) is True


def test_a_merely_late_run_is_not_missed(temp_db):
    job_id = temp_db.create_cron_job(
        name="f", prompt="x", schedule_kind="interval", interval_minutes=10
    )
    now = datetime.now()
    temp_db.update_cron_job_run_state(job_id, next_run_at=now - timedelta(seconds=40))
    assert is_missed_run(temp_db.get_cron_job(job_id), now) is False


def test_catch_up_run_once_never_skips(temp_db):
    job_id = temp_db.create_cron_job(
        name="g",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=10,
        catch_up="run_once",
    )
    now = datetime.now()
    temp_db.update_cron_job_run_state(job_id, next_run_at=now - timedelta(hours=5))
    assert is_missed_run(temp_db.get_cron_job(job_id), now) is False


def test_a_one_shot_is_never_skipped_however_late(temp_db):
    job_id = temp_db.create_cron_job(
        name="h",
        prompt="x",
        schedule_kind="once",
        run_at=datetime.now() - timedelta(days=2),
    )
    now = datetime.now()
    temp_db.update_cron_job_run_state(job_id, next_run_at=now - timedelta(days=2))
    assert is_missed_run(temp_db.get_cron_job(job_id), now) is False


# -- binding ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_bound_task_runs_inside_its_chat(temp_db, monkeypatch, runner):
    temp_db.create_chat(title="Work", config={}, chat_id="chat-1")
    job_id = temp_db.create_cron_job(
        name="recheck",
        prompt="look at the PR again",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-1",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    temp_db.update_cron_job_run_state(
        job_id, next_run_at=datetime.now() - timedelta(minutes=1)
    )

    await SchedulerBrain()._execute_job(job_id)

    assert runner.calls[0]["chat_id"] == "chat-1"
    assert "look at the PR again" in runner.calls[0]["reminder"]
    runs = temp_db.list_cron_runs(job_id)
    assert runs[0].status == "success"


@pytest.mark.asyncio
async def test_a_busy_chat_defers_a_bound_task_without_spending_a_retry(
    temp_db, monkeypatch, runner
):
    """Competing with the user is normal for a bound task, not a failure.

    Counting it as one would deactivate the task after five turns of ordinary
    conversation.
    """
    temp_db.create_chat(title="Work", config={}, chat_id="chat-2")
    job_id = temp_db.create_cron_job(
        name="recheck",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-2",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    before = datetime.now()
    temp_db.update_cron_job_run_state(job_id, next_run_at=before - timedelta(minutes=1))
    stream_controls["chat-2"] = StreamControl()
    try:
        await SchedulerBrain()._execute_job(job_id)
    finally:
        stream_controls.pop("chat-2", None)

    job = temp_db.get_cron_job(job_id)
    assert job.retry_count == 0
    assert job.active is True
    assert job.next_run_at > before
    assert temp_db.list_cron_runs(job_id) == []
    assert runner.calls == []


@pytest.mark.asyncio
async def test_a_quiet_bound_turn_leaves_no_trace(temp_db, monkeypatch, runner):
    temp_db.create_chat(title="Work", config={}, chat_id="chat-3")
    job_id = temp_db.create_cron_job(
        name="watch",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-3",
        suppress_ok=True,
        delivery_mode="announce",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    runner.response = ""  # the executor suppressed a nothing-to-report turn

    await SchedulerBrain()._execute_job(job_id)

    assert runner.calls[0]["suppress_ok"] is True
    assert temp_db.drain_background_notifications() == []


@pytest.mark.asyncio
async def test_a_one_shot_deactivates_after_it_runs(temp_db, monkeypatch, runner):
    temp_db.create_chat(title="Work", config={}, chat_id="chat-4")
    job_id = temp_db.create_cron_job(
        name="once",
        prompt="x",
        schedule_kind="once",
        run_at=datetime.now(),
        chat_id="chat-4",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)

    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    assert job.active is False
    assert job.next_run_at is None


@pytest.mark.asyncio
async def test_a_tick_will_not_fire_a_task_that_is_already_running(
    temp_db, monkeypatch, runner
):
    temp_db.create_chat(title="Work", config={}, chat_id="chat-5")
    job_id = temp_db.create_cron_job(
        name="slow",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-5",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    temp_db.update_cron_job_run_state(
        job_id, next_run_at=datetime.now() - timedelta(minutes=1)
    )

    brain = SchedulerBrain()
    brain._in_flight.add(job_id)
    await brain._tick()

    assert runner.calls == []


# -- heartbeat rows --------------------------------------------------------


def test_an_enabled_heartbeat_becomes_a_bound_interval_task(temp_db):
    temp_db.create_chat(
        title="Watched",
        chat_id="hb-1",
        config={"heartbeat_enabled": True, "heartbeat_interval_minutes": 20},
    )

    sync_heartbeat_tasks(temp_db)

    row = temp_db.find_cron_job_by_source("heartbeat", "hb-1")
    assert row.schedule_kind == "interval"
    assert row.interval_minutes == 20
    assert row.context_mode == "bound"
    assert row.suppress_ok is True
    assert row.delivery_mode == "none"


def test_syncing_twice_does_not_create_a_second_row(temp_db):
    temp_db.create_chat(
        title="Watched", config={"heartbeat_enabled": True}, chat_id="hb-2"
    )
    sync_heartbeat_tasks(temp_db)
    sync_heartbeat_tasks(temp_db)

    rows = [j for j in temp_db.list_cron_jobs() if j.chat_id == "hb-2"]
    assert len(rows) == 1


def test_changing_the_interval_re_arms_the_row(temp_db):
    temp_db.create_chat(
        title="Watched",
        chat_id="hb-3",
        config={"heartbeat_enabled": True, "heartbeat_interval_minutes": 30},
    )
    sync_heartbeat_tasks(temp_db)

    temp_db.merge_chat_config("hb-3", {"heartbeat_interval_minutes": 5})
    sync_heartbeat_tasks(temp_db)

    row = temp_db.find_cron_job_by_source("heartbeat", "hb-3")
    assert row.interval_minutes == 5


def test_disabling_heartbeat_puts_its_row_to_sleep(temp_db):
    temp_db.create_chat(
        title="Watched", config={"heartbeat_enabled": True}, chat_id="hb-4"
    )
    sync_heartbeat_tasks(temp_db)
    temp_db.merge_chat_config("hb-4", {"heartbeat_enabled": False})
    sync_heartbeat_tasks(temp_db)

    assert temp_db.find_cron_job_by_source("heartbeat", "hb-4").active is False


@pytest.mark.asyncio
async def test_a_due_heartbeat_is_offered_to_the_frontend_not_run_outright(
    temp_db, monkeypatch, runner
):
    """Heartbeats keep their pickup path so an open UI can stream the turn."""
    temp_db.create_chat(
        title="Watched", config={"heartbeat_enabled": True}, chat_id="hb-5"
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    sync_heartbeat_tasks(temp_db)
    row = temp_db.find_cron_job_by_source("heartbeat", "hb-5")

    await SchedulerBrain()._execute_job(row.id)

    assert runner.pending == ["hb-5"]
    assert runner.calls == []
    # No run history: a heartbeat is not a reportable task run.
    assert temp_db.list_cron_runs(row.id) == []


def test_a_bound_task_does_not_inherit_heartbeat_tool_approvals(temp_db):
    """Those tools were approved for a check-in the user configured.

    Handing the same blanket approval to an arbitrary scheduled prompt would
    widen it past what was agreed to.
    """
    from suzent.core.heartbeat import HeartbeatRunner

    runner = HeartbeatRunner()
    assert runner._build_config_override(["RunCommandTool"]).get("tool_approval_policy")
    assert "tool_approval_policy" not in runner._build_config_override([])


@pytest.mark.asyncio
async def test_the_scheduler_asks_for_no_heartbeat_approvals_on_a_plain_task(
    temp_db, monkeypatch, runner
):
    temp_db.create_chat(title="Work", config={}, chat_id="chat-6")
    job_id = temp_db.create_cron_job(
        name="recheck",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-6",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)

    await SchedulerBrain()._execute_job(job_id)

    assert runner.calls[0]["heartbeat_approvals"] is False


@pytest.mark.asyncio
async def test_a_dropped_heartbeat_handoff_comes_back_around(
    temp_db, monkeypatch, runner
):
    """Handing a heartbeat to the runner is not the same as it happening.

    The chat can go busy inside the pickup window, and both the frontend and
    the fallback then bow out. Claiming the run at hand-off would swallow that
    heartbeat for a whole interval.
    """
    temp_db.create_chat(
        title="Watched",
        config={"heartbeat_enabled": True, "heartbeat_interval_minutes": 30},
        chat_id="hb-6",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    sync_heartbeat_tasks(temp_db)
    row = temp_db.find_cron_job_by_source("heartbeat", "hb-6")

    brain = SchedulerBrain()
    await brain._execute_job(row.id)

    row = temp_db.get_cron_job(row.id)
    # Not recorded as run, and due again well before a full interval.
    assert row.last_run_at is None
    assert row.next_run_at < datetime.now() + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_a_heartbeat_that_did_run_advances_a_full_interval(
    temp_db, monkeypatch, runner
):
    """The runner stamps chat.config; the next sync turns that into the schedule."""
    temp_db.create_chat(
        title="Watched",
        config={"heartbeat_enabled": True, "heartbeat_interval_minutes": 30},
        chat_id="hb-7",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    sync_heartbeat_tasks(temp_db)
    row = temp_db.find_cron_job_by_source("heartbeat", "hb-7")
    await SchedulerBrain()._execute_job(row.id)

    ran_at = datetime.now(timezone.utc)
    temp_db.merge_chat_config("hb-7", {"heartbeat_last_run_at": ran_at.isoformat()})
    sync_heartbeat_tasks(temp_db)

    row = temp_db.get_cron_job(row.id)
    assert row.last_run_at is not None
    assert row.next_run_at > datetime.now() + timedelta(minutes=25)


@pytest.mark.asyncio
async def test_a_speaking_bound_task_reaches_the_transcript(
    temp_db, monkeypatch, runner
):
    """A task that is not suppressible exists to say something in that chat.

    Routed as a heartbeat it would skip message persistence, so its answer
    would be recorded as a successful run that never appears in the chat.
    """
    temp_db.create_chat(title="Work", config={}, chat_id="chat-7")
    job_id = temp_db.create_cron_job(
        name="report",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-7",
        suppress_ok=False,
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)

    await SchedulerBrain()._execute_job(job_id)

    assert runner.calls[0]["persist_to_chat"] is True


@pytest.mark.asyncio
async def test_a_quiet_bound_task_stays_out_of_the_transcript(
    temp_db, monkeypatch, runner
):
    temp_db.create_chat(title="Work", config={}, chat_id="chat-8")
    job_id = temp_db.create_cron_job(
        name="watch",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-8",
        suppress_ok=True,
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)

    await SchedulerBrain()._execute_job(job_id)

    # Rollback owns the message state for a turn that may be undone.
    assert runner.calls[0]["persist_to_chat"] is False


def test_a_quiet_task_is_told_the_exact_token_to_answer_with():
    """ "Stay silent" invites a polite "nothing to report", which is not a no-op.

    Suppression only fires on the token, so the reminder has to name it.
    """
    from suzent.core.heartbeat import HEARTBEAT_OK

    quiet = build_bound_task_reminder("watch", "check the build", quiet=True)
    loud = build_bound_task_reminder("report", "post the numbers", quiet=False)

    assert HEARTBEAT_OK in quiet
    assert HEARTBEAT_OK not in loud


@pytest.mark.asyncio
async def test_a_one_shot_is_recoverable_until_it_finishes(temp_db, monkeypatch):
    """A crash mid-turn must not retire the reminder without running it."""
    temp_db.create_chat(title="Work", config={}, chat_id="chat-9")
    job_id = temp_db.create_cron_job(
        name="remind",
        prompt="x",
        schedule_kind="once",
        run_at=datetime.now(),
        chat_id="chat-9",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)

    class _Dies:
        enabled = True

        async def run_bound_turn(self, *a, **k):
            raise RuntimeError("process died")

    monkeypatch.setattr("suzent.core.heartbeat.get_active_heartbeat", lambda: _Dies())
    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    # Still unspent, so a restart re-arms it from run_at instead of retiring it.
    assert job.last_run_at is None
    assert compute_next_run(job) is not None


@pytest.mark.asyncio
async def test_a_completed_one_shot_is_spent(temp_db, monkeypatch, runner):
    temp_db.create_chat(title="Work", config={}, chat_id="chat-10")
    job_id = temp_db.create_cron_job(
        name="remind",
        prompt="x",
        schedule_kind="once",
        run_at=datetime.now(),
        chat_id="chat-10",
    )
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)

    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    assert job.active is False
    assert job.last_run_at is not None
    assert compute_next_run(job) is None
