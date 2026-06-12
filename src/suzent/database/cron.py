from datetime import datetime
from typing import List, Optional

from sqlmodel import select

from .models import (
    CronJobModel,
    CronRunModel,
)


class CronOperationsMixin:
    def list_cron_jobs(self, active_only: bool = False) -> List[CronJobModel]:
        """List all cron jobs, optionally filtered to active only."""
        with self._session() as session:
            statement = select(CronJobModel).order_by(CronJobModel.created_at.desc())
            if active_only:
                statement = statement.where(CronJobModel.active.is_(True))  # noqa: E712
            return session.exec(statement).all()

    def get_cron_job(self, job_id: int) -> Optional[CronJobModel]:
        """Get a cron job by ID."""
        with self._session() as session:
            return session.get(CronJobModel, job_id)

    def create_cron_job(
        self,
        name: str,
        cron_expr: str,
        prompt: str,
        active: bool = True,
        delivery_mode: str = "announce",
        model_override: Optional[str] = None,
    ) -> int:
        """Create a new cron job and return its ID."""
        now = datetime.now()
        job = CronJobModel(
            name=name,
            cron_expr=cron_expr,
            prompt=prompt,
            active=active,
            delivery_mode=delivery_mode,
            model_override=model_override,
            created_at=now,
            updated_at=now,
        )
        with self._session() as session:
            session.add(job)
            session.commit()
            session.refresh(job)
            return job.id

    def update_cron_job(self, job_id: int, **kwargs) -> bool:
        """Update a cron job's configuration fields."""
        with self._session() as session:
            job = session.get(CronJobModel, job_id)
            if not job:
                return False
            for key, value in kwargs.items():
                if hasattr(job, key) and key not in ("id", "created_at"):
                    setattr(job, key, value)
            job.updated_at = datetime.now()
            session.add(job)
            session.commit()
            return True

    def delete_cron_job(self, job_id: int) -> bool:
        """Delete a cron job by ID."""
        with self._session() as session:
            job = session.get(CronJobModel, job_id)
            if not job:
                return False
            session.delete(job)
            session.commit()
            return True

    def update_cron_job_run_state(
        self,
        job_id: int,
        last_run_at: Optional[datetime] = None,
        next_run_at: Optional[datetime] = None,
        last_result: Optional[str] = None,
        last_error: Optional[str] = None,
        retry_count: Optional[int] = None,
        clear_error: bool = False,
    ) -> bool:
        """Update cron job run metadata (used by scheduler).

        Pass clear_error=True on a successful run to wipe any stale error from a
        previous failed run; otherwise last_error is left untouched when None.
        """
        with self._session() as session:
            job = session.get(CronJobModel, job_id)
            if not job:
                return False
            if last_run_at is not None:
                job.last_run_at = last_run_at
            if next_run_at is not None:
                job.next_run_at = next_run_at
            if last_result is not None:
                job.last_result = last_result[:2000]
            if clear_error:
                job.last_error = None
            elif last_error is not None:
                job.last_error = last_error[:1000]
            if retry_count is not None:
                job.retry_count = retry_count
            job.updated_at = datetime.now()
            session.add(job)
            session.commit()
            return True

    # -------------------------------------------------------------------------
    # Cron Run History
    # -------------------------------------------------------------------------

    def create_cron_run(self, job_id: int, started_at: datetime) -> int:
        """Create a run history record, return its ID."""
        run = CronRunModel(job_id=job_id, started_at=started_at)
        with self._session() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def finish_cron_run(
        self,
        run_id: int,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Mark a run as finished."""
        with self._session() as session:
            run = session.get(CronRunModel, run_id)
            if not run:
                return
            run.finished_at = datetime.now()
            run.status = status
            if result is not None:
                run.result = result[:2000]
            if error is not None:
                run.error = error[:1000]
            session.add(run)
            session.commit()

    def list_cron_runs(self, job_id: int, limit: int = 20) -> List[CronRunModel]:
        """List recent runs for a job."""
        with self._session() as session:
            statement = (
                select(CronRunModel)
                .where(CronRunModel.job_id == job_id)
                .order_by(CronRunModel.started_at.desc())
                .limit(limit)
            )
            return session.exec(statement).all()

    # -------------------------------------------------------------------------
    # API Key Operations
    # -------------------------------------------------------------------------
