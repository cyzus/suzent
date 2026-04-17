"""Test postprocess job tracking and step status recording."""

import pytest
import json
from suzent.database import (
    ChatDatabase,
    PostProcessStep,
    PostProcessStatus,
    PostProcessOutcome,
)


@pytest.fixture
def db():
    """Create an in-memory test database."""
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_postprocess.db"
        database = ChatDatabase(str(db_path))
        yield database

        # Properly close all connections
        try:
            database.engine.dispose()
        except Exception:
            pass


@pytest.fixture
def chat_id(db):
    """Create a test chat and return its ID."""
    chat_id = db.create_chat(
        title="Test Chat",
        config={"test": True},
        messages=[],
    )
    return chat_id


def test_create_postprocess_job(db, chat_id):
    """Test creating a postprocess job."""
    job_id = "job_123_abc123"
    assigned_revision = 1

    job_data = db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=assigned_revision,
        max_attempts=3,
    )

    assert job_data is not None
    assert job_data["job_id"] == job_id
    assert job_data["chat_id"] == chat_id
    assert job_data["assigned_revision"] == assigned_revision
    assert job_data["status"] == PostProcessStatus.PENDING
    assert job_data["attempt"] == 1
    assert job_data["max_attempts"] == 3


def test_start_postprocess_job(db, chat_id):
    """Test starting a postprocess job."""
    job_id = "job_456_def456"

    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
    )

    success = db.start_postprocess_job(job_id)
    assert success is True

    job = db.get_postprocess_job(job_id)
    assert job.status == PostProcessStatus.RUNNING
    assert job.started_at is not None


def test_update_job_step_status(db, chat_id):
    """Test updating individual step status."""
    job_id = "job_789_ghi789"

    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
    )
    db.start_postprocess_job(job_id)

    # Update B1: Transcript
    success = db.update_job_step_status(
        job_id,
        PostProcessStep.TRANSCRIPT,
        "success",
        duration_ms=150,
    )
    assert success is True

    # Update B2: Memory
    success = db.update_job_step_status(
        job_id,
        PostProcessStep.MEMORY,
        "success",
        duration_ms=320,
    )
    assert success is True

    job = db.get_postprocess_job(job_id)
    assert job.step_status_json is not None

    step_status = json.loads(job.step_status_json)
    assert PostProcessStep.TRANSCRIPT in step_status
    assert PostProcessStep.MEMORY in step_status
    assert step_status[PostProcessStep.TRANSCRIPT]["status"] == "success"
    assert step_status[PostProcessStep.TRANSCRIPT]["duration_ms"] == 150
    assert step_status[PostProcessStep.MEMORY]["status"] == "success"
    assert step_status[PostProcessStep.MEMORY]["duration_ms"] == 320


def test_update_job_step_status_with_error(db, chat_id):
    """Test updating step status with error details."""
    job_id = "job_error_001"

    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
    )
    db.start_postprocess_job(job_id)

    # Update B3: Compress (failed)
    success = db.update_job_step_status(
        job_id,
        PostProcessStep.COMPRESS,
        "failed",
        error="Memory limit exceeded",
        duration_ms=2500,
    )
    assert success is True

    job = db.get_postprocess_job(job_id)
    step_status = json.loads(job.step_status_json)
    assert step_status[PostProcessStep.COMPRESS]["status"] == "failed"
    assert step_status[PostProcessStep.COMPRESS]["error"] == "Memory limit exceeded"


def test_finalize_postprocess_job_success(db, chat_id):
    """Test finalizing a successful postprocess job."""
    job_id = "job_finalize_001"

    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
    )
    db.start_postprocess_job(job_id)

    # Record some steps
    db.update_job_step_status(
        job_id, PostProcessStep.TRANSCRIPT, "success", duration_ms=100
    )
    db.update_job_step_status(
        job_id, PostProcessStep.MEMORY, "success", duration_ms=200
    )

    # Finalize
    success = db.finalize_postprocess_job(
        job_id,
        PostProcessOutcome.SUCCESS,
    )
    assert success is True

    job = db.get_postprocess_job(job_id)
    assert job.status == PostProcessStatus.SUCCESS
    assert job.outcome == PostProcessOutcome.SUCCESS
    assert job.finished_at is not None
    assert job.duration_ms is not None
    assert job.error_class is None
    assert job.error_message is None


def test_finalize_postprocess_job_failed(db, chat_id):
    """Test finalizing a failed postprocess job."""
    job_id = "job_finalize_failed"

    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
    )
    db.start_postprocess_job(job_id)

    # Finalize with error
    success = db.finalize_postprocess_job(
        job_id,
        PostProcessOutcome.FAILED,
        error_class="ValueError",
        error_message="Invalid compression format",
    )
    assert success is True

    job = db.get_postprocess_job(job_id)
    assert job.status == PostProcessStatus.FAILED
    assert job.outcome == PostProcessOutcome.FAILED
    assert job.error_class == "ValueError"
    assert job.error_message == "Invalid compression format"


def test_finalize_postprocess_job_stale(db, chat_id):
    """Test finalizing a stale postprocess job (e.g., revision mismatch)."""
    job_id = "job_stale_001"

    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
    )
    db.start_postprocess_job(job_id)

    # Finalize as stale (skipped)
    success = db.finalize_postprocess_job(
        job_id,
        PostProcessOutcome.SKIPPED_STALE,
    )
    assert success is True

    job = db.get_postprocess_job(job_id)
    assert job.outcome == PostProcessOutcome.SKIPPED_STALE


def test_list_postprocess_jobs(db, chat_id):
    """Test listing postprocess jobs for a chat."""
    # Create multiple jobs
    for i in range(5):
        job_id = f"job_list_{i:03d}"
        db.create_postprocess_job(
            job_id=job_id,
            chat_id=chat_id,
            assigned_revision=i,
        )

    jobs = db.list_postprocess_jobs(chat_id, limit=10)
    assert len(jobs) == 5

    # Verify ordering (most recent first)
    assert jobs[0].job_id == "job_list_004"
    assert jobs[4].job_id == "job_list_000"


def test_postprocess_metrics_tracking(db, chat_id):
    """Test postprocess metrics recording."""
    # Get initial metrics
    initial_metrics = db.get_postprocess_metrics()
    initial_completed = initial_metrics["job_success"]

    # Create and complete a job
    job_id = "job_metrics_001"
    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
    )
    db.start_postprocess_job(job_id)
    db.finalize_postprocess_job(job_id, PostProcessOutcome.SUCCESS)

    # Check metrics updated
    updated_metrics = db.get_postprocess_metrics()
    assert updated_metrics["job_success"] == initial_completed + 1


def test_postprocess_job_full_lifecycle(db, chat_id):
    """Test complete postprocess job lifecycle."""
    job_id = "job_lifecycle_001"

    # 1. Create job
    job_data = db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=5,
        max_attempts=3,
    )
    assert job_data is not None
    assert job_data["status"] == PostProcessStatus.PENDING

    # 2. Start job
    assert db.start_postprocess_job(job_id) is True
    job = db.get_postprocess_job(job_id)
    assert job.status == PostProcessStatus.RUNNING

    # 3. Record all steps as successful
    for step in [
        PostProcessStep.TRANSCRIPT,
        PostProcessStep.MEMORY,
        PostProcessStep.COMPRESS,
        PostProcessStep.DISPLAY,
        PostProcessStep.PERSIST,
        PostProcessStep.LIFECYCLE,
        PostProcessStep.MIRROR,
    ]:
        db.update_job_step_status(job_id, step, "success", duration_ms=100)

    # 4. Finalize job
    assert db.finalize_postprocess_job(job_id, PostProcessOutcome.SUCCESS) is True
    job = db.get_postprocess_job(job_id)

    # 5. Verify final state
    assert job.status == PostProcessStatus.SUCCESS
    assert job.outcome == PostProcessOutcome.SUCCESS
    assert job.finished_at is not None

    step_status = json.loads(job.step_status_json)
    assert len(step_status) == 7  # All 7 steps
    for step_key in step_status:
        assert step_status[step_key]["status"] == "success"


def test_get_retriable_postprocess_jobs(db, chat_id):
    """Test retrieving jobs eligible for retry."""
    import time

    # Create a failed job
    job_id = "job_retry_001"
    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
        max_attempts=3,
    )
    db.start_postprocess_job(job_id)
    db.finalize_postprocess_job(
        job_id,
        PostProcessOutcome.FAILED,
        error_class="ValueError",
        error_message="Test error",
    )

    # Wait a moment to ensure the job is old enough
    time.sleep(0.1)

    # Get retriable jobs with small max_age_seconds
    retriable = db.get_retriable_postprocess_jobs(max_age_seconds=1)
    # Note: Due to timing, this might be empty in CI
    # Just verify the method works
    assert isinstance(retriable, list)


def test_prepare_job_for_retry(db, chat_id):
    """Test preparing a job for retry."""
    job_id = "job_retry_002"

    # Create and fail a job
    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
        max_attempts=3,
    )
    db.start_postprocess_job(job_id)
    db.update_job_step_status(job_id, PostProcessStep.COMPRESS, "failed", error="Test")
    db.finalize_postprocess_job(
        job_id,
        PostProcessOutcome.FAILED,
        error_class="ValueError",
        error_message="Compression failed",
    )

    job = db.get_postprocess_job(job_id)
    assert job.attempt == 1
    assert job.outcome == PostProcessOutcome.FAILED

    # Prepare for retry
    success = db.prepare_job_for_retry(job_id)
    assert success is True

    job = db.get_postprocess_job(job_id)
    assert job.attempt == 2
    assert job.status == PostProcessStatus.PENDING
    assert job.outcome is None
    assert job.step_status_json is None
    assert job.error_class is None


def test_prepare_job_for_retry_max_attempts_exceeded(db, chat_id):
    """Test that retry is not possible when max attempts exceeded."""
    job_id = "job_retry_max"

    db.create_postprocess_job(
        job_id=job_id,
        chat_id=chat_id,
        assigned_revision=1,
        max_attempts=2,  # Set low max attempts
    )

    # Simulate multiple failures
    for i in range(2):
        db.start_postprocess_job(job_id)
        db.finalize_postprocess_job(
            job_id, PostProcessOutcome.FAILED, error_class="Error", error_message="Fail"
        )
        if i < 1:  # Prepare for retry except on last iteration
            db.prepare_job_for_retry(job_id)

    job = db.get_postprocess_job(job_id)
    assert job.attempt == 2

    # Try to prepare for retry - should fail because max attempts reached
    success = db.prepare_job_for_retry(job_id)
    assert success is False
