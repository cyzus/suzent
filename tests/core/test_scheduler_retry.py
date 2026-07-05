from datetime import datetime, timedelta

import pytest

from suzent.core import scheduler as scheduler_mod
from suzent.core.scheduler import SchedulerBrain
from suzent.core.stream_registry import StreamControl, stream_controls


class _FailingProcessor:
    async def process_turn_text(self, **kwargs) -> str:
        raise RuntimeError("model unavailable")


@pytest.mark.asyncio
async def test_execute_job_retries_when_chat_processor_runtime_fails(
    temp_db, monkeypatch
):
    job_id = temp_db.create_cron_job(
        name="failing-job",
        cron_expr="*/5 * * * *",
        prompt="run this",
        active=True,
    )
    before = datetime.now()
    temp_db.update_cron_job_run_state(job_id, next_run_at=before - timedelta(minutes=1))

    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.core.chat_processor.ChatProcessor", _FailingProcessor)
    monkeypatch.setattr(SchedulerBrain, "_build_config_override", lambda *a, **k: {})

    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    assert job.retry_count == 1
    assert job.last_error == "model unavailable"
    assert job.next_run_at > before

    runs = temp_db.list_cron_runs(job_id)
    assert len(runs) == 1
    assert runs[0].status == "error"
    assert runs[0].error == "model unavailable"


@pytest.mark.asyncio
async def test_execute_job_defers_and_records_error_when_stream_is_active(
    temp_db, monkeypatch
):
    job_id = temp_db.create_cron_job(
        name="busy-job",
        cron_expr="*/5 * * * *",
        prompt="run this",
        active=True,
    )
    before = datetime.now()
    temp_db.update_cron_job_run_state(job_id, next_run_at=before - timedelta(minutes=1))

    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    chat_id = f"cron-{job_id}"
    stream_controls[chat_id] = StreamControl()
    try:
        await SchedulerBrain()._execute_job(job_id)
    finally:
        stream_controls.pop(chat_id, None)

    job = temp_db.get_cron_job(job_id)
    assert job.retry_count == 1
    assert job.last_error == "Previous cron run is still active"
    assert job.next_run_at > before

    runs = temp_db.list_cron_runs(job_id)
    assert len(runs) == 1
    assert runs[0].status == "error"
    assert runs[0].error == "Previous cron run is still active"
