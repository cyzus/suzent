"""Cron sidebar payload status tests."""

from datetime import datetime
from types import SimpleNamespace

from suzent.routes.cron_routes import _job_to_dict


def test_cron_job_payload_includes_session_status(monkeypatch) -> None:
    now = datetime.now()
    job = SimpleNamespace(
        id=7,
        name="Daily report",
        cron_expr="0 8 * * *",
        prompt="Write the report",
        active=True,
        delivery_mode="announce",
        model_override=None,
        retry_count=0,
        schedule_kind="cron",
        interval_minutes=None,
        run_at=None,
        timezone=None,
        jitter_seconds=0,
        catch_up="skip",
        chat_id=None,
        context_mode="isolated",
        suppress_ok=False,
        source="user",
        last_run_at=now,
        next_run_at=now,
        last_result=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    chat = SimpleNamespace(
        title="Cron: Daily report", updated_at=now, config={"unread_count": 4}
    )
    database = SimpleNamespace(
        get_chat=lambda _chat_id: chat,
        list_cron_runs=lambda _job_id, limit: [],
    )
    monkeypatch.setattr(
        "suzent.routes.cron_routes.is_background_streaming", lambda _chat_id: True
    )

    payload = _job_to_dict(job, database)

    assert payload["is_running"] is True
    assert payload["unread_count"] == 4


def test_a_bound_task_reports_the_chat_it_runs_in(monkeypatch) -> None:
    """An unbound task streams in cron-{id}; a bound one streams in its chat."""
    now = datetime.now()
    job = SimpleNamespace(
        id=7,
        name="Recheck",
        cron_expr="",
        prompt="look again",
        active=True,
        delivery_mode="silent",
        model_override=None,
        retry_count=0,
        schedule_kind="interval",
        interval_minutes=30,
        run_at=None,
        timezone=None,
        jitter_seconds=0,
        catch_up="skip",
        chat_id="chat-42",
        context_mode="bound",
        suppress_ok=True,
        source="agent",
        last_run_at=now,
        next_run_at=now,
        last_result=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    chat = SimpleNamespace(title="Work", updated_at=now, config={})
    database = SimpleNamespace(
        get_chat=lambda _chat_id: chat,
        list_cron_runs=lambda _job_id, limit: [],
    )
    seen: list[str] = []

    def _streaming(chat_id: str) -> bool:
        seen.append(chat_id)
        return False

    monkeypatch.setattr("suzent.routes.cron_routes.is_background_streaming", _streaming)

    payload = _job_to_dict(job, database)

    assert seen == ["chat-42"]
    assert payload["chat_id"] == "chat-42"
    assert payload["chat_title"] == "Work"
    assert payload["schedule_kind"] == "interval"
