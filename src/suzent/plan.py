from typing import Optional, List, Dict
from pydantic import BaseModel, Field

# Keep for backward compatibility and migration
import json
from enum import Enum

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

        
    def first_pending(self) -> Optional['Phase']:
        for t in self.phases:
            if t.status == "pending":
                return t
        return None

    def first_in_progress(self) -> Optional['Phase']:
        for t in self.phases:
            if t.status == "in_progress":
                return t
        return None


def read_plan_from_database(chat_id: str) -> Optional[Plan]:
    """Reads the plan from the database for a specific chat."""
    from suzent.database import get_database
    
    db = get_database()
    plan_data = db.get_plan(chat_id)
    
    if not plan_data:
        return None
    
    tasks = []
    for task_data in plan_data['tasks']:
        tasks.append(Phase(
            number=task_data['number'],
            description=task_data['description'],
            status=task_data['status'],
            note=task_data['note'],
            task_id=task_data.get('id'),
            capabilities=json.loads(task_data.get('capabilities', '{}')) if task_data.get('capabilities') else {},
            created_at=task_data.get('created_at'),
            updated_at=task_data.get('updated_at')
        ))
    
    return Plan(
        objective=plan_data['objective'],
        phases=tasks,
        chat_id=chat_id,
        id=plan_data.get('id'),
        created_at=plan_data.get('created_at'),
        updated_at=plan_data.get('updated_at')
    )


def read_plan_by_id(plan_id: int) -> Optional[Plan]:
    """Reads a specific plan by its identifier."""
    from suzent.database import get_database

    db = get_database()
    plan_data = db.get_plan_by_id(plan_id)
    if not plan_data:
        return None

    tasks = [
        Phase(
            number=task_data['number'],
            description=task_data['description'],
            status=task_data['status'],
            note=task_data['note'],
            task_id=task_data.get('id'),
            capabilities=json.loads(task_data.get('capabilities', '{}')) if task_data.get('capabilities') else {},
            created_at=task_data.get('created_at'),
            updated_at=task_data.get('updated_at'),
        )
        for task_data in plan_data['tasks']
    ]

    return Plan(
        objective=plan_data['objective'],
        phases=tasks,
        chat_id=plan_data.get('chat_id'),
        id=plan_data.get('id'),
        created_at=plan_data.get('created_at'),
        updated_at=plan_data.get('updated_at'),
    )


def read_plan_history_from_database(chat_id: str, limit: Optional[int] = None) -> list[Plan]:
    """Fetch all plan versions for a chat ordered by most recent first."""
    from suzent.database import get_database

    db = get_database()
    plan_rows = db.list_plans(chat_id, limit=limit)
    plans: list[Plan] = []

    for plan_data in plan_rows:
        tasks = []
        for task_data in plan_data['tasks']:
            tasks.append(Phase(
                number=task_data['number'],
                description=task_data['description'],
                status=task_data['status'],
                note=task_data['note'],
                task_id=task_data.get('id'),
                capabilities=json.loads(task_data.get('capabilities', '{}')) if task_data.get('capabilities') else {},
                created_at=task_data.get('created_at'),
                updated_at=task_data.get('updated_at')
            ))

        plans.append(Plan(
            objective=plan_data['objective'],
            phases=tasks,
            chat_id=plan_data.get('chat_id', chat_id),
            id=plan_data.get('id'),
            created_at=plan_data.get('created_at'),
            updated_at=plan_data.get('updated_at')
        ))

    return plans


def write_plan_to_database(plan: Plan, *, preserve_history: bool = True):
    """Persist the plan to the database.

    By default this records a new plan version so prior plans remain in history.
    Set preserve_history=False to update the latest plan record in place.
    """
    from suzent.database import get_database
    
    if not plan.chat_id:
        raise ValueError("Plan must have a chat_id to be saved to database")
    
    db = get_database()
    tasks_data = []
    for task in plan.phases:
        tasks_data.append({
            'number': task.number,
            'description': task.description,
            'status': task.status,
            'note': task.note,
            'capabilities': json.dumps(task.capabilities) if task.capabilities else None
        })
    
    if preserve_history:
        new_plan_id = db.create_plan(plan.chat_id, plan.objective, tasks_data)
        plan.id = new_plan_id
    else:
        db.update_plan(plan.chat_id, plan.objective, tasks_data, plan_id=plan.id)


def plan_to_dict(plan: Optional[Plan]) -> Optional[dict]:
    """Convert a Plan instance to a JSON-serialisable dictionary."""
    if not plan:
        return None


    data = plan.model_dump()
    
    # Computed version key logic
    if plan.id is not None:
        version_key = f"id:{plan.id}"
    elif plan.updated_at:
        version_key = f"updated:{plan.updated_at}"
    elif plan.created_at:
        version_key = f"created:{plan.created_at}"
    else:
        version_key = f"objective:{hash(plan.objective)}:{len(plan.phases)}"

    # Add/Update frontend-specific fields
    data["title"] = plan.objective
    data["versionKey"] = version_key
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
    if not plan:
        return
    if plan.first_in_progress():
        return
    pending = plan.first_pending()
    if pending:
        from suzent.database import get_database
        db = get_database()
        db.update_task_status(chat_id, pending.number, "in_progress")


def auto_complete_current(chat_id: str):
    """Mark the current in_progress task as completed."""
    plan = read_plan_from_database(chat_id)
    if not plan:
        return
    cur = plan.first_in_progress()
    if cur:
        from suzent.database import get_database
        db = get_database()
        db.update_task_status(chat_id, cur.number, "completed")
