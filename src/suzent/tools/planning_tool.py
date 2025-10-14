"""
This module provides a unified tool for creating and managing a plan in a TODO.md file.

The tool is inspired by the smolagents style, providing a single class to interact
with the plan. It supports creating a plan, checking its status, and updating steps.
"""
from typing import Optional

from smolagents.tools import Tool

from suzent.plan import (
    STATUS_MAP,
    Plan,
    Task,
    read_plan_from_database,
    read_plan_by_id,
    write_plan_to_database,
)
from suzent.database import get_database


class PlanningTool(Tool):
    """
    A tool that should be actively used to solve complex tasks or problems.
    """
    description: str = "A tool for managing a project plan in a TODO.md file."
    name: str = "PlanningTool"
    is_initialized: bool = False
    # Forward signature includes non-LLM exposed kwargs (e.g., chat_id), so skip strict validation.
    skip_forward_signature_validation = True

    def __init__(self):
        self._current_chat_id = None
        self._migrated_temp_plan = False
    
    def set_chat_context(self, chat_id: str):
        """Set the current chat context for this tool instance."""
        self._current_chat_id = chat_id
        if chat_id and chat_id != "planning_session_temp" and not self._migrated_temp_plan:
            try:
                db = get_database()
                migrated = db.reassign_plan_chat("planning_session_temp", chat_id)
                if migrated:
                    print(f"PlanningTool: migrated {migrated} temporary plan(s) to chat {chat_id}")
                self._migrated_temp_plan = True
            except Exception as exc:
                print(f"PlanningTool: failed migrating temporary plan to {chat_id}: {exc}")

    inputs = {
        "action": {
            "type": "string",
            "description": "The operation to perform. Must be one of 'create_plan', 'status', 'update_plan', or 'mark_step'."
        },
        "objective": {
            "type": "string",
            "description": "The high-level objective for the plan. Required for 'create_plan'.",
            "nullable": True
        },
        "action_items": {
            "type": "array",
            "description": "A list of action items for the plan. Required for 'create_plan'.",
            "nullable": True
        },
        "overwrite_plan_items": {
            "type": "array",
            "description": "A list of action items to overwrite the current plan. Required for 'update_plan'.",
            "nullable": True
        },
        "plan_id": {
            "type": "integer",
            "description": "ID of the plan to operate on when updating or marking steps.",
            "nullable": True
        },
        "step_number": {
            "type": "integer",
            "description": "The number of the step to mark. Required for 'mark_step'.",
            "nullable": True
        },
        "status": {
            "type": "string",
            "description": "The new status for the step. Required for 'mark_step'. Valid statuses are: pending, in_progress, completed, failed.",
            "nullable": True
        },
        "step_note": {
            "type": "string",
            "description": "A note to add or update for the step.",
            "nullable": True
        },
    }
    output_type = "string"

    def forward(
        self,
        action: str,
        objective: Optional[str] = None,
        action_items: Optional[list[str]] = None,
        overwrite_plan_items: Optional[list[str]] = None,
        plan_id: Optional[int] = None,
        step_number: Optional[int] = None,
        status: Optional[str] = None,
        step_note: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> str:
        """Manages a project plan in a TODO.md file."""
        action_map = {
            "create_plan": self._create_plan,
            "status": self._get_status,
            "update_plan": self._update_plan,
            "mark_step": self._mark_step,
        }

        if action not in action_map:
            return "Error: Invalid action. Must be one of 'create_plan', 'status', 'update_plan', or 'mark_step'."

        # Prioritize context chat_id over agent-provided chat_id
        context_chat_id = getattr(self, '_current_chat_id', None)
        if context_chat_id:
            print(f"PlanningTool: Using context chat_id: {context_chat_id} (overriding agent-provided: {chat_id})")
            chat_id = context_chat_id
        elif not chat_id:
            return (
                "Error: PlanningTool requires a chat_id. Ensure the agent is invoked with an active chat context."
            )
        else:
            print(f"PlanningTool: Using agent-provided chat_id: {chat_id}")
        
        # Prepare arguments for the respective methods
        args = {
            "create_plan": (chat_id, objective, action_items),
            "status": (chat_id, plan_id),
            "update_plan": (chat_id, plan_id, overwrite_plan_items),
            "mark_step": (chat_id, plan_id, step_number, status, step_note),
        }
        
        # Validate required arguments for the action
        required_args = {
            "create_plan": (objective, action_items),
            "update_plan": (overwrite_plan_items,),
            "mark_step": (step_number, status),
        }
        if any(arg is None for arg in required_args.get(action, [])):
            return f"Error: Missing required arguments for the '{action}' action."

        return action_map[action](*args[action])

    def _create_plan(self, chat_id: str, objective: str, action_items: list[str]) -> str:
        """Creates a new plan."""
        tasks = [Task(number=i + 1, description=item) for i, item in enumerate(action_items)]
        plan = Plan(objective=objective, tasks=tasks, chat_id=chat_id)
        write_plan_to_database(plan)
        return (
            f"Successfully created plan for Objective: {objective}\n"
            f"Plan ID: {plan.id if plan.id is not None else 'pending assignment'}\n\n"
            "Action Items:\n\n" + "\n".join([f"- {item}" for item in action_items])
        )

    def _get_status(self, chat_id: str, plan_id: Optional[int] = None) -> str:
        """Gets the current status of the plan."""
        plan = None
        if plan_id is not None:
            plan = read_plan_by_id(plan_id)
            if plan and plan.chat_id != chat_id:
                return f"Plan {plan_id} does not belong to chat {chat_id}."
        if not plan:
            plan = read_plan_from_database(chat_id)
        if not plan:
            return "No plan found. Please create a plan first using the 'create_plan' action."
        return plan.to_markdown()

    def _update_plan(self, chat_id: str, plan_id: Optional[int], overwrite_plan_items: list[str]) -> str:
        """Overwrites the current plan with new action items."""
        target_plan = None
        if plan_id is not None:
            target_plan = read_plan_by_id(plan_id)
            if target_plan and target_plan.chat_id != chat_id:
                return f"Plan {plan_id} does not belong to chat {chat_id}."
        if target_plan is None:
            target_plan = read_plan_from_database(chat_id)
            if target_plan and plan_id is None:
                print("PlanningTool: plan_id not provided; updating most recent plan.")
        if target_plan is None:
            return "No plan found to update. Please create a plan first."

        target_plan.tasks = [Task(number=i + 1, description=item) for i, item in enumerate(overwrite_plan_items)]
        write_plan_to_database(target_plan, preserve_history=False)
        return f"Successfully updated plan {target_plan.id} for chat {chat_id}"

    def _mark_step(self, chat_id: str, plan_id: Optional[int], step_number: int, status: str, step_note: Optional[str] = None) -> str:
        """Marks a step with a new status and optionally adds a note."""
        if status not in STATUS_MAP:
            return f"Invalid status. Valid statuses are: {list(STATUS_MAP.keys())}"

        db = get_database()
        success = db.update_task_status(chat_id, step_number, status, step_note, plan_id=plan_id)
        
        if not success:
            return f"Step {step_number} not found or no plan exists for this chat."

        # Get the updated plan to return its markdown representation
        plan = None
        if plan_id is not None:
            plan = read_plan_by_id(plan_id)
            if plan and plan.chat_id != chat_id:
                return f"Plan {plan_id} does not belong to chat {chat_id}."
        if not plan:
            plan = read_plan_from_database(chat_id)
            if plan and plan_id is None:
                print("PlanningTool: plan_id not provided; using most recent plan for status refresh.")
        if not plan:
            return f"Updated step {step_number} to {status}, but could not retrieve plan status."

        hide_completed = status == "completed"
        newly_completed_step = step_number if status == "completed" else None
        
        return f"Updated step {step_number} to {status}.\n\n" + plan.to_markdown(
            hide_completed=hide_completed,
            newly_completed_step=newly_completed_step
        )