"""
Plan management for agentic workflows.

Provides Phase and Plan models along with database persistence utilities.
"""

import json
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from suzent.database import PlanModel, TaskModel, get_database


class PhaseStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


STATUS_MAP = {
    PhaseStatus.PENDING: " ",
    PhaseStatus.IN_PROGRESS: ">",
    PhaseStatus.COMPLETED: "x",
}
REVERSE_STATUS_MAP = {v: k for k, v in STATUS_MAP.items()}


class Phase(BaseModel):
    """Represents a single phase in the plan."""

    number: int
    description: str
    status: PhaseStatus = PhaseStatus.PENDING
    note: Optional[str] = None
    task_id: Optional[int] = None
    capabilities: Dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_orm_model(cls, task: TaskModel) -> "Phase":
        """Create a Phase from a TaskModel."""
        capabilities = {}
        if task.capabilities:
            capabilities = json.loads(task.capabilities)

        return cls(
            number=task.number,
            description=task.description,
            status=task.status,
            note=task.note,
            task_id=task.id,
            capabilities=capabilities,
            created_at=task.created_at.isoformat() if task.created_at else None,
            updated_at=task.updated_at.isoformat() if task.updated_at else None,
        )

    def __str__(self):
        note_str = f" - Note: {self.note}" if self.note else ""
        return f"- [{STATUS_MAP[self.status]}] {self.number}. {self.description}{note_str}\n"


class Plan(BaseModel):
    """Represents the overall plan."""

    objective: str
    phases: List[Phase] = Field(default_factory=list)
    chat_id: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_orm_model(cls, plan: PlanModel) -> "Plan":
        """Create a Plan from a PlanModel."""
        phases = [Phase.from_orm_model(t) for t in plan.tasks]
        return cls(
            objective=plan.objective,
            phases=phases,
            chat_id=plan.chat_id,
            id=plan.id,
            created_at=plan.created_at.isoformat() if plan.created_at else None,
            updated_at=plan.updated_at.isoformat() if plan.updated_at else None,
        )

    def first_pending(self) -> Optional[Phase]:
        """Get the first pending phase."""
        return next((p for p in self.phases if p.status == PhaseStatus.PENDING), None)

    def first_in_progress(self) -> Optional[Phase]:
        """Get the first in-progress phase."""
        return next(
            (p for p in self.phases if p.status == PhaseStatus.IN_PROGRESS), None
        )


# -----------------------------------------------------------------------------
# Database Operations
# -----------------------------------------------------------------------------


def read_plan_from_database(chat_id: str) -> Optional[Plan]:
    """Reads the plan from the database for a specific chat."""
    plan_model = get_database().get_plan(chat_id)
    if not plan_model:
        return None
    return Plan.from_orm_model(plan_model)


def read_plan_by_id(plan_id: int) -> Optional[Plan]:
    """Reads a specific plan by its identifier."""
    plan_model = get_database().get_plan_by_id(plan_id)
    if not plan_model:
        return None
    return Plan.from_orm_model(plan_model)


def read_plan_history_from_database(
    chat_id: str,
    limit: Optional[int] = None,
) -> List[Plan]:
    """Fetch all plan versions for a chat ordered by most recent first."""
    plan_models = get_database().list_plans(chat_id, limit=limit)
    return [Plan.from_orm_model(p) for p in plan_models]


def write_plan_to_database(plan: Plan, *, preserve_history: bool = True):
    """Persist the plan to the database.

    By default this records a new plan version so prior plans remain in history.
    Set preserve_history=False to update the latest plan record in place.
    """
    if not plan.chat_id:
        raise ValueError("Plan must have a chat_id to be saved to database")

    db = get_database()
    tasks_data = [
        {
            "number": phase.number,
            "description": phase.description,
            "status": phase.status,
            "note": phase.note,
            "capabilities": json.dumps(phase.capabilities)
            if phase.capabilities
            else None,
        }
        for phase in plan.phases
    ]

    # create_plan handles upsert based on chat_id
    plan.id = db.create_plan(plan.chat_id, plan.objective, tasks_data)


def _compute_version_key(plan: Plan) -> str:
    """Compute a unique version key for the plan."""
    if plan.id is not None:
        return f"id:{plan.id}"
    if plan.updated_at:
        return f"updated:{plan.updated_at}"
    if plan.created_at:
        return f"created:{plan.created_at}"
    return f"objective:{hash(plan.objective)}:{len(plan.phases)}"


def plan_to_dict(plan: Optional[Plan]) -> Optional[dict]:
    """Convert a Plan instance to a JSON-serialisable dictionary."""
    if not plan:
        return None

    data = plan.model_dump()

    # Add frontend-specific fields
    data["title"] = plan.objective
    data["versionKey"] = _compute_version_key(plan)
    data["chatId"] = plan.chat_id
    data["createdAt"] = plan.created_at
    data["updatedAt"] = plan.updated_at

    # Enhance phases for frontend compatibility
    for phase_data in data["phases"]:
        phase_data["title"] = phase_data["description"]
        phase_data["createdAt"] = phase_data["created_at"]
        phase_data["updatedAt"] = phase_data["updated_at"]

    return data


def auto_mark_in_progress(chat_id: str):
    """If no task is in progress, mark the first pending as in_progress."""
    plan = read_plan_from_database(chat_id)
    if not plan or plan.first_in_progress():
        return

    pending = plan.first_pending()
    if pending:
        get_database().update_task_status(chat_id, pending.number, "in_progress")


def auto_complete_current(chat_id: str):
    """Mark the current in_progress task as completed."""
    plan = read_plan_from_database(chat_id)
    if not plan:
        return

    current = plan.first_in_progress()
    if current:
        get_database().update_task_status(chat_id, current.number, "completed")
