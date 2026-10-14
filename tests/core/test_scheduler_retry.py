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


_REJECTED = (
    "status_code: 400, model_name: gpt-x, body: {'message': \"Invalid "
    "'input[245].id': 'reasoning_content'.\"}"
)


class _RejectingProcessor:
    async def process_turn_text(self, **kwargs) -> str:
        raise RuntimeError(_REJECTED)


def _patch_scheduler(temp_db, monkeypatch, processor) -> None:
    monkeypatch.setattr(scheduler_mod, "get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.core.chat_processor.ChatProcessor", processor)
    monkeypatch.setattr(SchedulerBrain, "_build_config_override", lambda *a, **k: {})


@pytest.mark.asyncio
async def test_recurring_task_stays_active_after_exhausting_retries(
    temp_db, monkeypatch
):
    job_id = temp_db.create_cron_job(
        name="daily", cron_expr="0 9 * * *", prompt="run this", active=True
    )
    temp_db.update_cron_job_run_state(
        job_id,
        next_run_at=datetime.now() - timedelta(minutes=1),
        retry_count=scheduler_mod.MAX_RUN_RETRIES,
    )
    _patch_scheduler(temp_db, monkeypatch, _FailingProcessor)

    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    assert job.active
    assert job.retry_count == 0
    assert job.last_error == "model unavailable"
    expected = scheduler_mod.compute_next_run(job, after=datetime.now())
    assert job.next_run_at == expected


@pytest.mark.asyncio
async def test_one_shot_task_deactivates_after_exhausting_retries(temp_db, monkeypatch):
    job_id = temp_db.create_cron_job(
        name="reminder",
        schedule_kind="once",
        run_at=datetime.now() - timedelta(minutes=1),
        prompt="run this",
        active=True,
    )
    temp_db.update_cron_job_run_state(
        job_id,
        next_run_at=datetime.now() - timedelta(minutes=1),
        retry_count=scheduler_mod.MAX_RUN_RETRIES,
    )
    _patch_scheduler(temp_db, monkeypatch, _FailingProcessor)

    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    assert not job.active
    assert job.last_error.startswith("Max retries exceeded")


@pytest.mark.asyncio
async def test_rejected_request_skips_retries_and_waits_for_next_fire(
    temp_db, monkeypatch
):
    job_id = temp_db.create_cron_job(
        name="daily", cron_expr="0 9 * * *", prompt="run this", active=True
    )
    temp_db.update_cron_job_run_state(
        job_id, next_run_at=datetime.now() - timedelta(minutes=1)
    )
    _patch_scheduler(temp_db, monkeypatch, _RejectingProcessor)

    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    assert job.active
    assert job.retry_count == 0
    assert job.last_error.startswith("Not retried: status_code: 400")
    assert job.next_run_at == scheduler_mod.compute_next_run(job, after=datetime.now())


@pytest.mark.asyncio
async def test_retry_is_dropped_when_next_regular_fire_comes_first(
    temp_db, monkeypatch
):
    job_id = temp_db.create_cron_job(
        name="frequent", cron_expr="* * * * *", prompt="run this", active=True
    )
    temp_db.update_cron_job_run_state(
        job_id, next_run_at=datetime.now() - timedelta(seconds=10), retry_count=3
    )
    _patch_scheduler(temp_db, monkeypatch, _FailingProcessor)

    await SchedulerBrain()._execute_job(job_id)

    job = temp_db.get_cron_job(job_id)
    assert job.active
    assert job.retry_count == 0
    assert job.next_run_at - datetime.now() <= timedelta(minutes=1)


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        ("model unavailable", True),
        ("Request timed out.", True),
        ("status_code: 500, model_name: m, body: x", True),
        ("status_code: 429, model_name: m, body: x", True),
        ("status_code: 400, model_name: m, body: x", False),
        ("status_code: 401, model_name: m, body: x", False),
    ],
)
def test_is_retryable_error(error: str, retryable: bool):
    assert scheduler_mod._is_retryable_error(error) is retryable
