from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import select

from .models import GoalModel


class GoalOperationsMixin:
    def create_goal(
        self,
        project_id: str,
        objective: str,
        chat_id: Optional[str] = None,
        subgoals: Optional[List[str]] = None,
        max_turns: Optional[int] = None,
    ) -> GoalModel:
        """Create a new goal for a project, optionally owned by a specific chat."""
        now = datetime.now(timezone.utc)
        goal = GoalModel(
            project_id=project_id,
            chat_id=chat_id,
            objective=objective,
            subgoals=subgoals or [],
            max_turns=max_turns,
            created_at=now,
            updated_at=now,
        )
        with self._session() as session:
            session.add(goal)
            session.commit()
            session.refresh(goal)
            return goal

    def get_goal(
        self, project_id: str, chat_id: Optional[str] = None
    ) -> Optional[GoalModel]:
        """Return the active goal for a project, optionally scoped to a chat."""
        with self._session() as session:
            stmt = (
                select(GoalModel)
                .where(GoalModel.project_id == project_id)
                .where(GoalModel.status.in_(["active", "paused"]))
                .order_by(GoalModel.created_at.desc())
            )
            if chat_id is not None:
                stmt = stmt.where(GoalModel.chat_id == chat_id)
            return session.exec(stmt).first()

    def list_goals_for_project(self, project_id: str) -> List[GoalModel]:
        """Return all active/paused goals for a project (all chats)."""
        with self._session() as session:
            return list(
                session.exec(
                    select(GoalModel)
                    .where(GoalModel.project_id == project_id)
                    .where(GoalModel.status.in_(["active", "paused"]))
                    .order_by(GoalModel.created_at.desc())
                ).all()
            )

    def update_goal(self, goal_id: int, **kwargs) -> Optional[GoalModel]:
        """Update arbitrary fields on a goal."""
        with self._session() as session:
            goal = session.get(GoalModel, goal_id)
            if not goal:
                return None
            for key, value in kwargs.items():
                setattr(goal, key, value)
            goal.updated_at = datetime.now(timezone.utc)
            session.add(goal)
            session.commit()
            session.refresh(goal)
            return goal

    def clear_goal(self, project_id: str, chat_id: Optional[str] = None) -> None:
        """Mark the active goal as completed, optionally scoped to a chat."""
        with self._session() as session:
            stmt = (
                select(GoalModel)
                .where(GoalModel.project_id == project_id)
                .where(GoalModel.status.in_(["active", "paused"]))
            )
            if chat_id is not None:
                stmt = stmt.where(GoalModel.chat_id == chat_id)
            goal = session.exec(stmt).first()
            if goal:
                goal.status = "completed"
                goal.completed_at = datetime.now(timezone.utc)
                goal.updated_at = datetime.now(timezone.utc)
                session.add(goal)
                session.commit()
