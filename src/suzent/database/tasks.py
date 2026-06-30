from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import select

from suzent.core.goal_task_events import emit_goal_task_changed

from .models import TaskModel


class TaskOperationsMixin:
    def create_task(
        self,
        project_id: str,
        title: str,
        description: str,
        chat_id: Optional[str] = None,
        active_form: Optional[str] = None,
        status: str = "pending",
        assignee: Optional[str] = None,
        blocks: Optional[List[int]] = None,
        blocked_by: Optional[List[int]] = None,
    ) -> TaskModel:
        """Create a new task for a project, optionally owned by a specific chat."""
        now = datetime.now(timezone.utc)
        task = TaskModel(
            project_id=project_id,
            chat_id=chat_id,
            title=title,
            description=description,
            active_form=active_form,
            status=status,
            assignee=assignee,
            blocks=blocks or [],
            blocked_by=blocked_by or [],
            created_at=now,
            updated_at=now,
        )
        with self._session() as session:
            session.add(task)
            session.commit()
            session.refresh(task)
            emit_goal_task_changed(
                entity="task",
                action="created",
                project_id=task.project_id,
                chat_id=task.chat_id,
                task_id=task.id,
            )
            return task

    def get_task(self, task_id: int) -> Optional[TaskModel]:
        """Return a task by id, or None."""
        with self._session() as session:
            return session.get(TaskModel, task_id)

    def list_tasks(
        self,
        project_id: str,
        chat_id: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        include_completed: bool = False,
        include_cancelled: bool = False,
    ) -> List[TaskModel]:
        """Return tasks for a project, optionally scoped to a chat."""
        with self._session() as session:
            stmt = select(TaskModel).where(TaskModel.project_id == project_id)
            if chat_id is not None:
                stmt = stmt.where(TaskModel.chat_id == chat_id)
            if status:
                stmt = stmt.where(TaskModel.status == status)
            else:
                if not include_completed:
                    stmt = stmt.where(TaskModel.status != "completed")
                if not include_cancelled:
                    stmt = stmt.where(TaskModel.status != "cancelled")
            if assignee:
                stmt = stmt.where(TaskModel.assignee == assignee)
            stmt = stmt.order_by(TaskModel.created_at.asc())
            return list(session.exec(stmt).all())

    def update_task(self, task_id: int, **kwargs) -> Optional[TaskModel]:
        """Update arbitrary fields on a task."""
        with self._session() as session:
            task = session.get(TaskModel, task_id)
            if not task:
                return None
            for key, value in kwargs.items():
                setattr(task, key, value)
            task.updated_at = datetime.now(timezone.utc)
            session.add(task)
            session.commit()
            session.refresh(task)
            emit_goal_task_changed(
                entity="task",
                action="updated",
                project_id=task.project_id,
                chat_id=task.chat_id,
                task_id=task.id,
            )
            return task

    def delete_task(self, task_id: int) -> bool:
        """Delete a task. Returns True if deleted, False if not found."""
        with self._session() as session:
            task = session.get(TaskModel, task_id)
            if not task:
                return False
            project_id = task.project_id
            chat_id = task.chat_id
            session.delete(task)
            session.commit()
            emit_goal_task_changed(
                entity="task",
                action="deleted",
                project_id=project_id,
                chat_id=chat_id,
                task_id=task_id,
            )
            return True
