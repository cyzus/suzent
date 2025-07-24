"""
This module provides a unified tool for creating and managing a plan in a TODO.md file.

The tool is inspired by the smolagents style, providing a single class to interact
with the plan. It supports creating a plan, checking its status, and updating steps.
"""

import re
from pathlib import Path
from typing import Optional

from smolagents.tools import Tool

TODO_FILE = Path("TODO.md")

STATUS_MAP = {
    "pending": " ",
    "in_progress": ">",
    "completed": "x",
    "failed": "!",
}
REVERSE_STATUS_MAP = {v: k for k, v in STATUS_MAP.items()}


class PlanningTool(Tool):
    """
    A tool for managing a project plan in a TODO.md file.
    """
    description: str = "A tool for managing a project plan in a TODO.md file."
    name: str = "PlanningTool"
    def __init__(self):
        pass
    inputs: dict[str, dict[str, str | type | bool]] = {
        "action": {"type": "string", "description": "The operation to perform. Must be one of 'create', 'status', or 'update'."},
        "objective": {"type": "string", "description": "The high-level objective for the plan. Required for the 'create' action.", "nullable": True},
        "step_number": {"type": "integer", "description": "The number of the step to update. Required for the 'update' action.", "nullable": True},
        "status": {"type": "string", "description": "The new status for the step. Required for the 'update' action. Valid statuses are: pending, in_progress, completed, failed.", "nullable": True},
    }
    output_type: str = "string"

    def forward(
        self,
        action: str,
        objective: Optional[str] = None,
        step_number: Optional[int] = None,
        status: Optional[str] = None,
    ) -> str:
        """
        Manages a project plan in a TODO.md file.

        Args:
            action: The operation to perform. Must be one of 'create', 'status', or 'update'.
            objective: The high-level objective for the plan. Required for the 'create' action.
            step_number: The number of the step to update. Required for the 'update' action.
            status: The new status for the step. Required for the 'update' action.
                    Valid statuses are: pending, in_progress, completed, failed.

        Returns:
            A string indicating the result of the action.
        """
        if action == "create":
            if not objective:
                return "Error: 'objective' is required for the 'create' action."
            return self._initialize_plan(objective)
        elif action == "status":
            return self._get_plan_status()
        elif action == "update":
            if not step_number or not status:
                return "Error: 'step_number' and 'status' are required for the 'update' action."
            return self._update_step_status(step_number, status)
        else:
            return "Error: Invalid action. Must be one of 'create', 'status', or 'update'."

    def _initialize_plan(self, objective: str) -> str:
        """Creates a TODO.md file with a plan to achieve the objective."""
        plan_steps = [
            "Define the requirements and scope of the objective.",
            "Break down the objective into smaller, manageable tasks.",
            "Identify the necessary tools and resources for each task.",
            "Create a timeline and set milestones for the project.",
            "Execute the plan, monitoring progress and making adjustments as needed.",
            "Conduct a final review to ensure the objective has been met.",
        ]

        with open(TODO_FILE, "w") as f:
            f.write(f"# Plan for: {objective}\n\n")
            for i, step in enumerate(plan_steps):
                f.write(f"- [ ] {i+1}. {step}\n")
        
        return f"Successfully created plan in {TODO_FILE}"

    def _get_plan_status(self) -> str:
        """Reads and parses the TODO.md file to return a status string."""
        if not TODO_FILE.exists():
            return "No plan found. Please create a plan first using the 'create' action."
        
        with open(TODO_FILE, "r") as f:
            content = f.read()

        tasks = []
        for match in re.finditer(r"- \[(.)\] (\d+)\. (.*)", content):
            status_char = match.group(1)
            status = REVERSE_STATUS_MAP.get(status_char, "unknown")
            tasks.append(f"Step {match.group(2)}: {match.group(3).strip()} - **{status.upper()}**")

        if not tasks:
            return "The plan is empty or in an invalid format."

        return "\n".join(tasks)

    def _update_step_status(self, step_number: int, new_status: str) -> str:
        """Updates the status of a step in the TODO.md file."""
        if new_status not in STATUS_MAP:
            return f"Invalid status. Valid statuses are: {list(STATUS_MAP.keys())}"

        if not TODO_FILE.exists():
            return "TODO.md file not found."

        with open(TODO_FILE, "r") as f:
            lines = f.readlines()

        updated = False
        for i, line in enumerate(lines):
            if re.match(rf"- \[(.)\] {step_number}\.", line.strip()):
                new_status_char = STATUS_MAP[new_status]
                lines[i] = re.sub(r"- \[(.)\]", f"- [{new_status_char}]", line)
                updated = True
                break

        if not updated:
            return f"Step {step_number} not found."

        with open(TODO_FILE, "w") as f:
            f.writelines(lines)

        return f"Updated step {step_number} to {new_status}."