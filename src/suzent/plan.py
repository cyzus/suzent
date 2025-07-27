import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

TODO_FILE = Path("TODO.md")

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

    def __str__(self):
        note_str = f" - Note: {self.note}" if self.note else ""
        return f"- [{STATUS_MAP[self.status]}] {self.number}. {self.description}{note_str}\n"


@dataclass
class Plan:
    """Represents the overall plan."""
    objective: str
    tasks: list[Task] = field(default_factory=list)

    def to_markdown(self, hide_completed: bool = False, newly_completed_step: Optional[int] = None) -> str:
        """Converts the plan to a markdown string."""
        markdown = f"### Current Plan for Objective: {self.objective}\n\n"
        visible_tasks = []
        for task in self.tasks:
            if hide_completed and task.status == "completed" and task.number != newly_completed_step:
                continue
            task_item = f"- Step {task.number}: {task.description} - **{task.status.upper()}**"
            if task.note:
                task_item += f" (Note: {task.note})"
            visible_tasks.append(task_item)
        markdown += "\n".join(visible_tasks)
        return markdown


def read_plan_from_file() -> Optional[Plan]:
    """Reads the plan from the TODO.md file."""
    if not TODO_FILE.exists():
        return None

    content = TODO_FILE.read_text()
    objective_match = re.search(r"# Plan for: (.*)", content)
    objective = objective_match.group(1).strip() if objective_match else "Unknown Objective"

    tasks = []
    for match in re.finditer(r"- \[(.)\] (\d+)\. (.*?)(?: - Note: (.*))?$", content, re.MULTILINE):
        status_char, num_str, desc, note = match.groups()
        tasks.append(Task(
            number=int(num_str),
            description=desc.strip(),
            status=REVERSE_STATUS_MAP.get(status_char, "unknown"),
            note=note.strip() if note else None
        ))
    return Plan(objective=objective, tasks=tasks)


def write_plan_to_file(plan: Plan):
    """Writes the plan to the TODO.md file."""
    with open(TODO_FILE, "w") as f:
        f.write(f"# Plan for: {plan.objective}\n\n")
        for task in plan.tasks:
            f.write(str(task))
