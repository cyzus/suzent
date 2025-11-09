"""
This module provides a unified tool for creating and managing a plan.

The tool is inspired by the smolagents style, providing a single class to interact
with the plan. It supports creating a plan, checking its status, and updating steps.
"""
from typing import Optional

from smolagents.tools import Tool

from suzent.logger import get_logger
from suzent.plan import (
    STATUS_MAP,
    Plan,
    Task,
    read_plan_from_database,
    read_plan_by_id,
    write_plan_to_database,
)
from suzent.database import get_database

logger = get_logger(__name__)


class PlanningTool(Tool):
    """
    A tool that should be actively used to solve complex tasks or problems.
    """
    description: str = "A tool for managing a plan to solve a complex task or problem."
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
                    logger.info(f"Migrated {migrated} temporary plan(s) to chat {chat_id}")
                self._migrated_temp_plan = True
            except Exception as exc:
                logger.error(f"Failed migrating temporary plan to {chat_id}: {exc}")

    inputs = {
        "action": {
            "type": "string",
            "description": "The operation to perform.",
            "enum": ["create_plan", "status", "update_plan", "mark_step"]
        },
        "objective": {
            "type": "string",
            "description": "The high-level objective for the plan. Required for 'create_plan'.",
            "nullable": True
        },
        "action_items": {
            "type": "array",
            "description": "A list of action items (3-5 is recommended). Required for 'create_plan' and 'update_plan'.",
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
            "description": "The new status for the step. Required for 'mark_step'.",
            "enum": ["pending", "in_progress", "completed", "failed"],
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
            return self._format_error("Invalid action", f"Must be one of: {', '.join(action_map.keys())}")

        # Resolve chat_id (context takes priority)
        chat_id = self._resolve_chat_id(chat_id)
        if not chat_id:
            return self._format_error("Missing chat_id", "Ensure the agent is invoked with an active chat context")
        
        # Validate required arguments
        validation_error = self._validate_action_args(action, objective, action_items, step_number, status)
        if validation_error:
            return validation_error
        
        # Prepare arguments for the respective methods
        args = {
            "create_plan": (chat_id, objective, action_items),
            "status": (chat_id, plan_id),
            "update_plan": (chat_id, plan_id, action_items),
            "mark_step": (chat_id, plan_id, step_number, status, step_note),
        }

        return action_map[action](*args[action])
    
    def _resolve_chat_id(self, provided_chat_id: Optional[str]) -> Optional[str]:
        """Resolve the chat_id, prioritizing context over provided value."""
        context_chat_id = getattr(self, '_current_chat_id', None)
        if context_chat_id:
            logger.debug(f"Using context chat_id: {context_chat_id}")
            return context_chat_id
        if provided_chat_id:
            logger.debug(f"Using provided chat_id: {provided_chat_id}")
            return provided_chat_id
        return None
    
    def _validate_action_args(
        self, 
        action: str, 
        objective: Optional[str],
        action_items: Optional[list[str]],
        step_number: Optional[int],
        status: Optional[str]
    ) -> Optional[str]:
        """Validate that required arguments are provided for the action."""
        if action == "create_plan" and (not objective or not action_items):
            return self._format_error("Missing arguments", "create_plan requires 'objective' and 'action_items'")
        if action == "update_plan" and not action_items:
            return self._format_error("Missing arguments", "update_plan requires 'action_items'")
        if action == "mark_step" and (step_number is None or not status):
            return self._format_error("Missing arguments", "mark_step requires 'step_number' and 'status'")
        return None
    
    def _format_error(self, title: str, message: str) -> str:
        """Format error messages in markdown."""
        return f"**Error: {title}**\n\n{message}"
    
    def _format_success(self, title: str, details: Optional[str] = None) -> str:
        """Format success messages in markdown."""
        if details:
            return f"✓ **{title}**\n\n{details}"
        return f"✓ **{title}**"

    def _get_plan(self, chat_id: str, plan_id: Optional[int]) -> Optional[Plan]:
        """Retrieve a plan by ID or most recent for chat_id."""
        plan = None
        
        if plan_id is not None:
            plan = read_plan_by_id(plan_id)
            if plan and plan.chat_id != chat_id:
                logger.warning(f"Plan {plan_id} does not belong to chat {chat_id}")
                return None
        
        if not plan:
            plan = read_plan_from_database(chat_id)
            if plan and plan_id is None:
                logger.debug("Using most recent plan for chat")
        
        return plan

    def _create_plan(self, chat_id: str, objective: str, action_items: list[str]) -> str:
        """Creates a new plan."""
        tasks = [Task(number=i + 1, description=item) for i, item in enumerate(action_items)]
        plan = Plan(objective=objective, tasks=tasks, chat_id=chat_id)
        write_plan_to_database(plan)
        
        # Return the plan in markdown format directly
        return f"✓ **Plan created** (ID: {plan.id or 'pending'})\n\n{plan.to_markdown()}"

    def _get_status(self, chat_id: str, plan_id: Optional[int] = None) -> str:
        """Gets the current status of the plan."""
        plan = self._get_plan(chat_id, plan_id)
        
        if not plan:
            if plan_id is not None:
                return self._format_error("Plan not found", f"No plan with ID {plan_id} found for this chat")
            return self._format_error("No plan exists", "Create a plan first using 'create_plan'")
        
        return plan.to_markdown()

    def _update_plan(self, chat_id: str, plan_id: Optional[int], action_items: list[str]) -> str:
        """Overwrites the current plan with new action items."""
        plan = self._get_plan(chat_id, plan_id)
        
        if not plan:
            if plan_id is not None:
                return self._format_error("Plan not found", f"No plan with ID {plan_id} found for this chat")
            return self._format_error("No plan exists", "Create a plan first using 'create_plan'")

        plan.tasks = [Task(number=i + 1, description=item) for i, item in enumerate(action_items)]
        write_plan_to_database(plan, preserve_history=False)
        
        return f"✓ **Plan updated**\n\n{plan.to_markdown()}"

    def _mark_step(self, chat_id: str, plan_id: Optional[int], step_number: int, status: str, step_note: Optional[str] = None) -> str:
        """Marks a step with a new status and optionally adds a note."""
        if status not in STATUS_MAP:
            valid_statuses = ", ".join(STATUS_MAP.keys())
            return self._format_error("Invalid status", f"Valid statuses: {valid_statuses}")

        db = get_database()
        success = db.update_task_status(chat_id, step_number, status, step_note, plan_id=plan_id)
        
        if not success:
            return self._format_error("Update failed", f"Step {step_number} not found or no plan exists")

        # Get updated plan to show current state
        plan = self._get_plan(chat_id, plan_id)
        if not plan:
            return self._format_success(f"Step {step_number} → {status}")

        # When marking a task as completed, show only remaining tasks
        if status == "completed":
            plan_status = plan.to_markdown(hide_completed=True, newly_completed_step=None)
            return f"✓ **Step {step_number} completed**\n\n{plan_status}"
        
        # For other status changes, show all tasks
        plan_status = plan.to_markdown(hide_completed=False, newly_completed_step=None)
        return f"✓ **Step {step_number} → {status}**\n\n{plan_status}"