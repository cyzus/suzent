"""ScheduleTool: the agent arranging its own future turns, within bounds."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from suzent.tools import schedule_tool as schedule_mod
from suzent.tools.schedule_tool import MAX_AGENT_TASKS_PER_CHAT, ScheduleTool


@pytest.fixture
def tool(temp_db, monkeypatch):
    monkeypatch.setattr(schedule_mod, "get_database", lambda: temp_db)
    temp_db.create_chat(title="Work", config={}, chat_id="chat-1")
    return ScheduleTool()


def ctx(chat_id="chat-1"):
    return SimpleNamespace(deps=SimpleNamespace(chat_id=chat_id))


def test_a_delayed_task_binds_to_the_current_chat(tool, temp_db):
    result = tool.forward(
        ctx(), action="create", name="recheck CI", prompt="look again", in_minutes=20
    )

    assert result.success
    job = temp_db.get_cron_job(result.metadata["task_id"])
    assert job.chat_id == "chat-1"
    assert job.context_mode == "bound"
    assert job.schedule_kind == "once"
    assert job.source == "agent"
    assert job.next_run_at > datetime.now() + timedelta(minutes=19)


def test_opting_out_of_binding_gives_the_task_its_own_chat(tool, temp_db):
    result = tool.forward(
        ctx(),
        action="create",
        name="digest",
        prompt="summarise",
        every_minutes=60,
        bind_to_chat=False,
    )

    job = temp_db.get_cron_job(result.metadata["task_id"])
    assert job.context_mode == "isolated"
    # The originating chat is still recorded: it is ownership, not placement.
    assert job.chat_id == "chat-1"
    # An isolated task has nowhere to speak, so it announces instead.
    assert job.delivery_mode == "announce"


def test_isolated_tasks_still_count_against_the_quota(tool):
    """Otherwise one chat could spawn unlimited isolated tasks."""
    for i in range(MAX_AGENT_TASKS_PER_CHAT):
        assert tool.forward(
            ctx(),
            action="create",
            name=f"t{i}",
            prompt="x",
            every_minutes=30,
            bind_to_chat=False,
        ).success

    overflow = tool.forward(
        ctx(), action="create", prompt="x", every_minutes=30, bind_to_chat=False
    )
    assert not overflow.success


def test_an_isolated_task_can_still_be_listed_and_cancelled(tool, temp_db):
    """A task the agent cannot see is a task it can never stop."""
    created = tool.forward(
        ctx(),
        action="create",
        name="digest",
        prompt="x",
        every_minutes=30,
        bind_to_chat=False,
    )
    task_id = created.metadata["task_id"]

    assert "digest" in tool.forward(ctx(), action="list").message
    assert tool.forward(ctx(), action="cancel", task_id=task_id).success
    assert temp_db.get_cron_job(task_id) is None


def test_exactly_one_schedule_must_be_given(tool):
    both = tool.forward(
        ctx(), action="create", prompt="x", in_minutes=10, every_minutes=10
    )
    neither = tool.forward(ctx(), action="create", prompt="x")

    assert not both.success and not neither.success


def test_a_prompt_is_required(tool):
    assert not tool.forward(ctx(), action="create", in_minutes=10).success


def test_a_too_eager_interval_is_refused(tool):
    """A repeating task wakes the agent, which could schedule another one."""
    result = tool.forward(ctx(), action="create", prompt="x", every_minutes=1)

    assert not result.success
    assert "at least" in result.message


def test_a_cron_that_fires_faster_than_the_floor_is_refused(tool):
    result = tool.forward(ctx(), action="create", prompt="x", cron="* * * * *")

    assert not result.success
    assert "floor" in result.message


def test_a_cron_that_is_tight_for_only_part_of_its_cycle_is_refused(tool):
    """A cron schedule is not uniform.

    "0-50 * * * *" fires every minute for most of the hour; only the gap
    straddling :50-:00 is ten minutes. Sampling the first two occurrences can
    land on exactly that gap and wave the whole expression through.
    """
    result = tool.forward(ctx(), action="create", prompt="x", cron="0-50 * * * *")

    assert not result.success
    assert "floor" in result.message


def test_a_genuinely_sparse_cron_is_still_allowed(tool):
    assert tool.forward(ctx(), action="create", prompt="x", cron="0 9 * * 1-5").success


def test_an_invalid_cron_is_refused(tool):
    assert not tool.forward(ctx(), action="create", prompt="x", cron="nonsense").success


def test_a_past_timestamp_is_refused(tool):
    past = (datetime.now() - timedelta(hours=1)).isoformat()
    result = tool.forward(ctx(), action="create", prompt="x", at=past)

    assert not result.success
    assert "past" in result.message


def test_a_chat_cannot_accumulate_unbounded_tasks(tool):
    for i in range(MAX_AGENT_TASKS_PER_CHAT):
        assert tool.forward(
            ctx(), action="create", name=f"t{i}", prompt="x", in_minutes=30
        ).success

    overflow = tool.forward(ctx(), action="create", prompt="x", in_minutes=30)
    assert not overflow.success
    assert "Cancel one" in overflow.message


def test_listing_shows_only_this_chats_tasks(tool, temp_db):
    temp_db.create_chat(title="Other", config={}, chat_id="chat-2")
    tool.forward(ctx(), action="create", name="mine", prompt="x", in_minutes=30)
    tool.forward(
        ctx("chat-2"), action="create", name="theirs", prompt="x", in_minutes=30
    )

    listing = tool.forward(ctx(), action="list")
    assert "mine" in listing.message
    assert "theirs" not in listing.message


def test_cancelling_removes_the_task(tool, temp_db):
    created = tool.forward(ctx(), action="create", prompt="x", in_minutes=30)
    task_id = created.metadata["task_id"]

    assert tool.forward(ctx(), action="cancel", task_id=task_id).success
    assert temp_db.get_cron_job(task_id) is None


def test_the_agent_cannot_cancel_a_task_the_user_set_up(tool, temp_db):
    """A heartbeat or a human's cron job is not the agent's to remove."""
    job_id = temp_db.create_cron_job(
        name="user's heartbeat",
        prompt="x",
        schedule_kind="interval",
        interval_minutes=30,
        chat_id="chat-1",
        source="heartbeat",
    )

    result = tool.forward(ctx(), action="cancel", task_id=job_id)

    assert not result.success
    assert temp_db.get_cron_job(job_id) is not None


def test_a_task_belonging_to_another_chat_is_invisible(tool, temp_db):
    temp_db.create_chat(title="Other", config={}, chat_id="chat-2")
    other = tool.forward(ctx("chat-2"), action="create", prompt="x", in_minutes=30)

    result = tool.forward(ctx(), action="cancel", task_id=other.metadata["task_id"])
    assert not result.success


def test_updating_the_interval_re_arms_the_task(tool, temp_db):
    created = tool.forward(
        ctx(), action="create", prompt="x", every_minutes=60, name="poll"
    )
    task_id = created.metadata["task_id"]

    assert tool.forward(
        ctx(), action="update", task_id=task_id, every_minutes=10
    ).success

    job = temp_db.get_cron_job(task_id)
    assert job.interval_minutes == 10
    assert job.next_run_at < datetime.now() + timedelta(minutes=11)


def test_an_update_still_respects_the_interval_floor(tool):
    created = tool.forward(ctx(), action="create", prompt="x", every_minutes=60)

    result = tool.forward(
        ctx(), action="update", task_id=created.metadata["task_id"], every_minutes=1
    )
    assert not result.success


def test_a_turn_without_a_chat_cannot_schedule(tool):
    assert not tool.forward(ctx(None), action="list").success
