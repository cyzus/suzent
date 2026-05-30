import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlmodel import select

from .models import (
    ChatModel,
    PostprocessJobModel,
    PostProcessOutcome,
    PostProcessStatus,
    _postprocess_metrics,
)


def _get_job_by_job_id(session, job_id: str):
    return session.exec(
        select(PostprocessJobModel).where(PostprocessJobModel.job_id == job_id)
    ).first()


class PostprocessOperationsMixin:
    def create_postprocess_job(
        self,
        job_id: str,
        chat_id: str,
        assigned_revision: int,
        max_attempts: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Create a new postprocess job record.

        Args:
            job_id: UUID-based unique job identifier
            chat_id: Chat ID for this job
            assigned_revision: Revision from Phase A snapshot
            max_attempts: Max retry attempts (default: 3)

        Returns:
            Dict with job data if successful, None otherwise.
        """
        now = datetime.now()
        with self._session() as session:
            # Verify chat exists
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return None

            job = PostprocessJobModel(
                job_id=job_id,
                chat_id=chat_id,
                assigned_revision=assigned_revision,
                status=PostProcessStatus.PENDING,
                attempt=1,
                max_attempts=max_attempts,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()

            # Increment metrics
            _postprocess_metrics.job_started += 1

            # Return dict representation while still in session context
            return {
                "id": job.id,
                "job_id": job.job_id,
                "chat_id": job.chat_id,
                "assigned_revision": job.assigned_revision,
                "status": job.status,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
            }

    def start_postprocess_job(self, job_id: str) -> bool:
        """Mark a postprocess job as running."""
        now = datetime.now()
        with self._session() as session:
            job = _get_job_by_job_id(session, job_id)
            if not job:
                return False

            job.status = PostProcessStatus.RUNNING
            job.started_at = now
            job.updated_at = now
            session.add(job)
            session.commit()
            return True

    def update_job_step_status(
        self,
        job_id: str,
        step: str,
        status: str,
        error: str = None,
        duration_ms: int = None,
    ) -> bool:
        """Update status of a specific step within a postprocess job.

        Args:
            job_id: Job identifier
            step: Step name (B1_transcript, B2_memory, etc.)
            status: Step status (pending, running, success, failed)
            error: Error message if failed
            duration_ms: Duration of the step in milliseconds

        Returns:
            True if updated successfully, False if job not found.
        """
        now = datetime.now()
        with self._session() as session:
            job = _get_job_by_job_id(session, job_id)
            if not job:
                return False

            # Parse or initialize step_status_json
            try:
                step_status = json.loads(job.step_status_json or "{}")
            except (json.JSONDecodeError, TypeError):
                step_status = {}

            # Update step status
            step_status[step] = {
                "status": status,
                "error": error,
                "duration_ms": duration_ms,
                "updated_at": now.isoformat(),
            }

            job.step_status_json = json.dumps(step_status)
            job.updated_at = now
            session.add(job)
            session.commit()
            return True

    def finalize_postprocess_job(
        self,
        job_id: str,
        outcome: str,
        error_class: str = None,
        error_message: str = None,
    ) -> bool:
        """Mark a postprocess job as complete.

        Args:
            job_id: Job identifier
            outcome: Outcome code (success, failed, skipped_stale)
            error_class: Exception class name if failed
            error_message: Error details if failed

        Returns:
            True if finalized successfully, False if job not found.
        """
        now = datetime.now()
        with self._session() as session:
            job = _get_job_by_job_id(session, job_id)
            if not job:
                return False

            job.status = (
                PostProcessStatus.SUCCESS
                if outcome == PostProcessOutcome.SUCCESS
                else PostProcessStatus.SKIPPED_STALE
                if outcome == PostProcessOutcome.SKIPPED_STALE
                else PostProcessStatus.FAILED
            )
            job.outcome = outcome
            job.finished_at = now
            job.error_class = error_class
            job.error_message = error_message

            if job.started_at:
                job.duration_ms = int((now - job.started_at).total_seconds() * 1000)

            job.updated_at = now
            session.add(job)
            session.commit()

            # Update metrics
            if outcome == PostProcessOutcome.SUCCESS:
                _postprocess_metrics.job_success += 1
                _postprocess_metrics.total_duration_ms += job.duration_ms or 0
            elif outcome == PostProcessOutcome.SKIPPED_STALE:
                _postprocess_metrics.job_skipped_stale += 1
            else:
                _postprocess_metrics.job_failed += 1

            return True

    def get_postprocess_job(self, job_id: str) -> Optional[PostprocessJobModel]:
        """Retrieve a postprocess job by ID."""
        with self._session() as session:
            return _get_job_by_job_id(session, job_id)

    def list_postprocess_jobs(
        self, chat_id: str, limit: int = 50
    ) -> List[PostprocessJobModel]:
        """List postprocess jobs for a specific chat."""
        with self._session() as session:
            statement = (
                select(PostprocessJobModel)
                .where(PostprocessJobModel.chat_id == chat_id)
                .order_by(PostprocessJobModel.created_at.desc())
                .limit(limit)
            )
            return session.exec(statement).all()

    def get_postprocess_metrics(self) -> Dict[str, Any]:
        """Get current postprocess metrics."""
        return {
            "snapshot_committed": _postprocess_metrics.snapshot_committed,
            "snapshot_failed": _postprocess_metrics.snapshot_failed,
            "job_started": _postprocess_metrics.job_started,
            "job_success": _postprocess_metrics.job_success,
            "job_failed": _postprocess_metrics.job_failed,
            "job_skipped_stale": _postprocess_metrics.job_skipped_stale,
            "total_duration_ms": _postprocess_metrics.total_duration_ms,
        }

    def get_retriable_postprocess_jobs(
        self, max_age_seconds: int = 3600
    ) -> List[PostprocessJobModel]:
        """Get postprocess jobs eligible for retry.

        Criteria:
        - Status is 'failed' (not 'skipped_stale')
        - attempt < max_attempts
        - Not recently attempted (to avoid retry storms)

        Args:
            max_age_seconds: Only retry jobs older than this (default: 1 hour)

        Returns:
            List of PostprocessJobModel objects eligible for retry.
        """
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)

        with self._session() as session:
            statement = (
                select(PostprocessJobModel)
                .where(PostprocessJobModel.outcome == PostProcessOutcome.FAILED)
                .where(PostprocessJobModel.attempt < PostprocessJobModel.max_attempts)
                .where(PostprocessJobModel.updated_at < cutoff)
                .order_by(PostprocessJobModel.updated_at.asc())
                .limit(10)
            )
            return session.exec(statement).all()

    def prepare_job_for_retry(self, job_id: str) -> bool:
        """Prepare a job for retry by incrementing attempt count and resetting status.

        Args:
            job_id: Job identifier

        Returns:
            True if prepared successfully, False if job not found or not eligible.
        """
        now = datetime.now()
        with self._session() as session:
            job = _get_job_by_job_id(session, job_id)
            if not job:
                return False

            # Only reset if currently failed or needs retry
            if job.outcome != PostProcessOutcome.FAILED:
                return False

            if job.attempt >= job.max_attempts:
                return False

            job.attempt += 1
            job.status = PostProcessStatus.PENDING
            job.outcome = None
            job.started_at = None
            job.finished_at = None
            job.duration_ms = None
            job.error_class = None
            job.error_message = None
            job.step_status_json = None
            job.updated_at = now

            session.add(job)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Plan Operations
    # -------------------------------------------------------------------------
