import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Keep for backward compatibility and migration
STATUS_MAP = {
    "pending": " ",
    "in_progress": ">",
    "completed": "x",
    "failed": "!",
}
REVERSE_STATUS_MAP = {v: k for k, v in STATUS_MAP.items()}


@dataclass
class Task:
    """Represents a single task in the plan."""
    number: int
    description: str
    status: str = "pending"
    note: Optional[str] = None
    task_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __str__(self):
        note_str = f" - Note: {self.note}" if self.note else ""
        return f"- [{STATUS_MAP[self.status]}] {self.number}. {self.description}{note_str}\n"


@dataclass
class Plan:
    """Represents the overall plan."""
    objective: str
    tasks: list[Task] = field(default_factory=list)
    chat_id: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_markdown(self, hide_completed: bool = False, newly_completed_step: Optional[int] = None) -> str:
        """Converts the plan to a markdown string."""
        # Status icons for visual clarity
        status_icons = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✓",
            "failed": "✗"
        }
        
        # Show progress summary if hiding completed tasks
        if hide_completed:
            completed_count = sum(1 for t in self.tasks if t.status == "completed")
            remaining_count = len(self.tasks) - completed_count
            if completed_count > 0:
                markdown = f"**{self.objective}** — {remaining_count} remaining ({completed_count} done)\n\n"
            else:
                markdown = f"**{self.objective}**\n\n"
        else:
            markdown = f"**{self.objective}**\n\n"
        
        visible_tasks = []
        
        for task in self.tasks:
            if hide_completed and task.status == "completed" and task.number != newly_completed_step:
                continue
            
            icon = status_icons.get(task.status, "•")
            # Show step number in brackets to clarify it's the original step ID
            task_item = f"**[{task.number}]** {icon} {task.description}"
            
            if task.note:
                task_item += f"\n      *{task.note}*"
            
            visible_tasks.append(task_item)
        
        markdown += "\n".join(visible_tasks)
        
        return markdown

    def first_pending(self) -> Optional['Task']:
        for t in self.tasks:
            if t.status == "pending":
                return t
        return None

    def first_in_progress(self) -> Optional['Task']:
        for t in self.tasks:
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
        tasks.append(Task(
            number=task_data['number'],
            description=task_data['description'],
            status=task_data['status'],
            note=task_data['note'],
            task_id=task_data.get('id'),
            created_at=task_data.get('created_at'),
            updated_at=task_data.get('updated_at')
        ))
    
    return Plan(
        objective=plan_data['objective'],
        tasks=tasks,
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
        Task(
            number=task_data['number'],
            description=task_data['description'],
            status=task_data['status'],
            note=task_data['note'],
            task_id=task_data.get('id'),
            created_at=task_data.get('created_at'),
            updated_at=task_data.get('updated_at'),
        )
        for task_data in plan_data['tasks']
    ]

    return Plan(
        objective=plan_data['objective'],
        tasks=tasks,
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
            tasks.append(Task(
                number=task_data['number'],
                description=task_data['description'],
                status=task_data['status'],
                note=task_data['note'],
                task_id=task_data.get('id'),
                created_at=task_data.get('created_at'),
                updated_at=task_data.get('updated_at')
            ))

        plans.append(Plan(
            objective=plan_data['objective'],
            tasks=tasks,
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
    for task in plan.tasks:
        tasks_data.append({
            'number': task.number,
            'description': task.description,
            'status': task.status,
            'note': task.note
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

    if plan.id is not None:
        version_key = f"id:{plan.id}"
    elif plan.updated_at:
        version_key = f"updated:{plan.updated_at}"
    elif plan.created_at:
        version_key = f"created:{plan.created_at}"
    else:
        version_key = f"objective:{hash(plan.objective)}:{len(plan.tasks)}"

    return {
        "id": plan.id,
        "chatId": plan.chat_id,
        "objective": plan.objective,
        "title": plan.objective,
        "createdAt": plan.created_at,
        "updatedAt": plan.updated_at,
        "versionKey": version_key,
        "tasks": [
            {
                "id": task.task_id,
                "number": task.number,
                "description": task.description,
                "status": task.status,
                "note": task.note,
                "createdAt": task.created_at,
                "updatedAt": task.updated_at,
            }
            for task in plan.tasks
        ],
    }


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
