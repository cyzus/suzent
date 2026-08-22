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
        last_run_at=now,
        next_run_at=now,
        last_result=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    chat = SimpleNamespace(updated_at=now, config={"unread_count": 4})
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
