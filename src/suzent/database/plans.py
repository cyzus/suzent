from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import selectinload
from sqlmodel import select

from .models import (
    PlanModel,
    TaskModel,
)


def _sort_plan_tasks(plan: "PlanModel") -> "PlanModel":
    plan.tasks.sort(key=lambda t: t.number)
    return plan


class PlanOperationsMixin:
    def create_plan(
        self,
        chat_id: str,
        objective: str,
        tasks: List[Dict[str, Any]] = None,
    ) -> int:
        """Create or update the single plan for a chat and return its ID."""
        now = datetime.now()
        tasks = tasks or []

        with self._session() as session:
            # Check for existing plan
            statement = select(PlanModel).where(PlanModel.chat_id == chat_id).limit(1)
            existing_plan = session.exec(statement).first()

            if existing_plan:
                plan_id = existing_plan.id
                existing_plan.objective = objective
                existing_plan.updated_at = now
                session.add(existing_plan)

                # Delete existing tasks
                task_stmt = select(TaskModel).where(TaskModel.plan_id == plan_id)
                for task in session.exec(task_stmt).all():
                    session.delete(task)
            else:
                # Create new plan
                new_plan = PlanModel(
                    chat_id=chat_id,
                    objective=objective,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_plan)
                session.commit()
                session.refresh(new_plan)
                plan_id = new_plan.id

            # Create tasks
            for task_data in tasks:
                task = TaskModel(
                    plan_id=plan_id,
                    number=task_data.get("number"),
                    description=task_data.get("description"),
                    status=task_data.get("status", "pending"),
                    note=task_data.get("note"),
                    capabilities=task_data.get("capabilities"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(task)

            session.commit()
            return plan_id

    def get_plan(self, chat_id: str) -> Optional[PlanModel]:
        """Get the latest plan for a specific chat."""
        with self._session() as session:
            statement = (
                select(PlanModel)
                .where(PlanModel.chat_id == chat_id)
                .order_by(PlanModel.created_at.desc())
                .options(selectinload(PlanModel.tasks))
                .limit(1)
            )
            plan = session.exec(statement).first()
            if not plan:
                return None

            return _sort_plan_tasks(plan)

    def get_plan_by_id(self, plan_id: int) -> Optional[PlanModel]:
        """Fetch a plan and its tasks by plan ID."""
        with self._session() as session:
            statement = (
                select(PlanModel)
                .where(PlanModel.id == plan_id)
                .options(selectinload(PlanModel.tasks))
            )
            plan = session.exec(statement).first()
            if not plan:
                return None

            return _sort_plan_tasks(plan)

    def list_plans(
        self,
        chat_id: str,
        limit: Optional[int] = None,
    ) -> List[PlanModel]:
        """Return all plans for a chat ordered by newest first."""
        with self._session() as session:
            statement = (
                select(PlanModel)
                .where(PlanModel.chat_id == chat_id)
                .order_by(PlanModel.created_at.desc())
                .options(selectinload(PlanModel.tasks))
            )
            if limit is not None:
                statement = statement.limit(limit)

            plans = session.exec(statement).all()
            for plan in plans:
                _sort_plan_tasks(plan)
            return plans

    def update_plan_objective(self, plan_id: int, objective: str) -> bool:
        """Update the objective of a plan."""
        with self._session() as session:
            plan = session.get(PlanModel, plan_id)
            if not plan:
                return False

            plan.objective = objective
            plan.updated_at = datetime.now()
            session.add(plan)
            session.commit()
            return True

    def create_task(self, plan_id: int, description: str, number: int) -> Optional[int]:
        """Add a new task to a plan."""
        now = datetime.now()
        with self._session() as session:
            plan = session.get(PlanModel, plan_id)
            if not plan:
                return None

            task = TaskModel(
                plan_id=plan_id,
                description=description,
                number=number,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return task.id

    def update_task_status(
        self,
        chat_id: str,
        task_number: int,
        status: str,
        note: str = None,
        plan_id: Optional[int] = None,
    ) -> bool:
        """Update the status and optionally note of a specific task."""
        now = datetime.now()

        with self._session() as session:
            # Find the plan
            if plan_id is not None:
                plan = session.get(PlanModel, plan_id)
                if plan and plan.chat_id != chat_id:
                    plan = None
            else:
                statement = (
                    select(PlanModel)
                    .where(PlanModel.chat_id == chat_id)
                    .order_by(PlanModel.created_at.desc())
                    .limit(1)
                )
                plan = session.exec(statement).first()

            if not plan:
                return False

            # Find and update the task
            task_stmt = select(TaskModel).where(
                (TaskModel.plan_id == plan.id) & (TaskModel.number == task_number)
            )
            task = session.exec(task_stmt).first()

            if not task:
                return False

            task.status = status
            task.updated_at = now
            if note is not None:
                task.note = note

            session.add(task)
            session.commit()
            return True

    def update_task(
        self,
        task_id: int,
        status: str = None,
        description: str = None,
        note: str = None,
        capabilities: str = None,
    ) -> bool:
        """Update a task's details."""
        with self._session() as session:
            task = session.get(TaskModel, task_id)
            if not task:
                return False

            if status:
                task.status = status
            if description:
                task.description = description
            if note:
                task.note = note
            if capabilities:
                task.capabilities = capabilities

            task.updated_at = datetime.now()
            session.add(task)
            session.commit()
            return True

    def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        with self._session() as session:
            task = session.get(TaskModel, task_id)
            if not task:
                return False
            session.delete(task)
            session.commit()
            return True

    def delete_plan(self, chat_id: str) -> bool:
        """Delete the plan for a specific chat."""
        with self._session() as session:
            statement = select(PlanModel).where(PlanModel.chat_id == chat_id)
            plans = session.exec(statement).all()

            if not plans:
                return False

            for plan in plans:
                session.delete(plan)

            session.commit()
            return True

    # -------------------------------------------------------------------------
    # User Preferences Operations
    # -------------------------------------------------------------------------
