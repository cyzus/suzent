"""Editing a task's schedule through the API must not silently unschedule it."""

import json
from datetime import datetime, timedelta

import pytest
from starlette.requests import Request

from suzent.routes.cron_routes import update_cron_job


def request(job_id: int, payload: object) -> Request:
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(payload).encode(),
            "more_body": False,
        }

    scope = {
        "type": "http",
        "method": "PUT",
        "path": f"/cron/jobs/{job_id}",
        "headers": [],
        "path_params": {"job_id": str(job_id)},
    }
    return Request(scope, receive)


@pytest.fixture
def one_shot(temp_db, monkeypatch):
    monkeypatch.setattr("suzent.routes.cron_routes.get_database", lambda: temp_db)
    job_id = temp_db.create_cron_job(
        name="remind",
        prompt="x",
        schedule_kind="once",
        run_at=datetime.now() + timedelta(hours=2),
    )
    temp_db.update_cron_job_run_state(
        job_id, next_run_at=datetime.now() + timedelta(hours=2)
    )
    return job_id


@pytest.mark.asyncio
async def test_an_unparseable_run_at_is_refused(temp_db, one_shot):
    """Falling back to the stored timestamp would validate the old value and
    then write the unparseable one, retiring the task behind a 200."""
    response = await update_cron_job(request(one_shot, {"run_at": "not a timestamp"}))

    assert response.status_code == 400
    job = temp_db.get_cron_job(one_shot)
    assert job.run_at is not None
    assert job.next_run_at is not None
    assert job.active is True


@pytest.mark.asyncio
async def test_clearing_run_at_on_a_one_shot_is_refused(temp_db, one_shot):
    response = await update_cron_job(request(one_shot, {"run_at": None}))

    assert response.status_code == 400
    assert temp_db.get_cron_job(one_shot).run_at is not None


@pytest.mark.asyncio
async def test_a_valid_new_timestamp_is_accepted_and_re_arms(temp_db, one_shot):
    when = (datetime.now() + timedelta(days=1)).replace(microsecond=0)

    response = await update_cron_job(request(one_shot, {"run_at": when.isoformat()}))

    assert response.status_code == 200
    job = temp_db.get_cron_job(one_shot)
    assert job.run_at == when
    assert job.next_run_at == when


@pytest.mark.asyncio
async def test_editing_only_the_prompt_leaves_the_schedule_alone(temp_db, one_shot):
    before = temp_db.get_cron_job(one_shot).next_run_at

    response = await update_cron_job(request(one_shot, {"prompt": "something else"}))

    assert response.status_code == 200
    job = temp_db.get_cron_job(one_shot)
    assert job.prompt == "something else"
    assert job.next_run_at == before
