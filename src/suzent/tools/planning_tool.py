"""
This module provides a unified tool for creating and managing a plan.

The tool is inspired by the smolagents style, providing a single class to interact
with the plan. It supports creating a plan, checking its status, and updating steps.
"""

from typing import Optional

from smolagents.tools import Tool

from suzent.logger import get_logger
from suzent.plan import (
    Plan,
    Phase,
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

    description: str = "A tool for managing a plan to do a complex task or problem."
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
        if (
            chat_id
            and chat_id != "planning_session_temp"
            and not self._migrated_temp_plan
        ):
            try:
                db = get_database()
                migrated = db.reassign_plan_chat("planning_session_temp", chat_id)
                if migrated:
                    logger.info(
                        f"Migrated {migrated} temporary plan(s) to chat {chat_id}"
                    )
                self._migrated_temp_plan = True
            except Exception as exc:
                logger.error(f"Failed migrating temporary plan to {chat_id}: {exc}")

    inputs = {
        "action": {
            "type": "string",
            "description": "The operation to perform.",
            "enum": ["update", "advance"],
        },
        "goal": {
            "type": "string",
            "description": "A concise high-level goal for the plan. Required for 'update' if creating a new plan or changing goal.",
            "nullable": True,
        },
        "phases": {
            "type": "array",
            "description": "A list of phases with id, title, and capabilities (a dictionary of capability_name: capability_description). Required for 'update'.",
            "nullable": True,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title": {"type": "string"},
                    "capabilities": {"type": "object"},
                },
                "required": ["id", "title"],
            },
        },
        "current_phase_id": {
            "type": "integer",
            "description": "The ID of the phase currently finishing. Required for 'advance'.",
            "nullable": True,
        },
        "next_phase_id": {
            "type": "integer",
            "description": "The ID of the next phase to start. Required for 'advance'.",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(
        self,
        action: str,
        goal: Optional[str] = None,
        phases: Optional[list[Phase]] = None,
        current_phase_id: Optional[int] = None,
        next_phase_id: Optional[int] = None,
        chat_id: Optional[str] = None,
    ) -> str:
        """Manages a project plan."""
        action_map = {
            "update": self._update_plan,
            "advance": self._advance_plan,
        }

        if action not in action_map:
            return self._format_error(
                "Invalid action", f"Must be one of: {', '.join(action_map.keys())}"
            )

        # Resolve chat_id (context takes priority)
        chat_id = self._resolve_chat_id(chat_id)
        if not chat_id:
            return self._format_error(
                "Missing chat_id",
                "Ensure the agent is invoked with an active chat context",
            )

        # Validate required arguments
        validation_error = self._validate_action_args(
            action, goal, phases, current_phase_id, next_phase_id
        )
        if validation_error:
            return validation_error

        # Prepare arguments for the respective methods
        args = {
            "update": (chat_id, goal, phases),
            "advance": (chat_id, current_phase_id, next_phase_id),
        }

        return action_map[action](*args[action])

    def _resolve_chat_id(self, provided_chat_id: Optional[str]) -> Optional[str]:
        """Resolve the chat_id, prioritizing context over provided value."""
        context_chat_id = getattr(self, "_current_chat_id", None)
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
        goal: Optional[str],
        phases: Optional[list[dict]],
        current_phase_id: Optional[int],
        next_phase_id: Optional[int],
    ) -> Optional[str]:
        """Validate that required arguments are provided for the action."""
        if action == "update" and not phases:
            return self._format_error("Missing arguments", "update requires 'phases'")
        if action == "advance" and (current_phase_id is None or next_phase_id is None):
            return self._format_error(
                "Missing arguments",
                "advance requires 'current_phase_id' and 'next_phase_id'",
            )
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

    def _update_plan(
        self, chat_id: str, goal: Optional[str], phases: list[dict]
    ) -> str:
        """Create or update a plan."""
        existing_plan = self._get_plan(chat_id, None)
        objective = (
            goal if goal else (existing_plan.objective if existing_plan else "No Goal")
        )

        # Map phases to Phase objects
        new_phases = []
        for p in phases:
            new_phases.append(
                Phase(
                    number=p["id"],
                    description=p["title"],
                    capabilities=p.get("capabilities", {}),
                )
            )

        # Ensure first phase is in_progress if none are
        if not any(p.status == "in_progress" for p in new_phases) and not any(
            p.status == "completed" for p in new_phases
        ):
            if new_phases:
                new_phases[0].status = "in_progress"

        plan = Plan(objective=objective, phases=new_phases, chat_id=chat_id)
        if existing_plan:
            plan.id = existing_plan.id  # Keep ID to update in place if desired, though write_plan creates new version by default

        write_plan_to_database(
            plan, preserve_history=True
        )  # Always create history for updates generally good

        return self._format_plan_output(plan, "Task plan updated")

    def _advance_plan(
        self, chat_id: str, current_phase_id: int, next_phase_id: int
    ) -> str:
        """Advance the plan from current phase to next."""
        plan = self._get_plan(chat_id, None)
        if not plan:
            return self._format_error(
                "No plan exists", "Create a plan first using 'update'"
            )

        # Find phases
        try:
            next_phase_idx = next(
                i for i, p in enumerate(plan.phases) if p.number == next_phase_id
            )
        except StopIteration:
            return self._format_error(
                "Invalid next_phase_id", f"Phase {next_phase_id} not found"
            )

        current_phase = next(
            (p for p in plan.phases if p.number == current_phase_id), None
        )
        if not current_phase:
            return self._format_error(
                "Invalid current_phase_id", f"Phase {current_phase_id} not found"
            )

        next_phase = plan.phases[next_phase_idx]

        # Mark all phases before the next phase as completed (handling skips)
        for i in range(next_phase_idx):
            plan.phases[i].status = "completed"

        next_phase.status = "in_progress"

        write_plan_to_database(plan, preserve_history=True)

        return self._format_plan_output(
            plan,
            "Advanced to the next phase",
            previous_phase=current_phase,
            next_phase=next_phase,
        )

    def _format_plan_output(
        self,
        plan: Plan,
        header: str,
        previous_phase: Optional[Phase] = None,
        next_phase: Optional[Phase] = None,
    ) -> str:
        """Format the plan output as requested."""
        phases_str = "; ".join([f"{p.number}: {p.description}" for p in plan.phases])
        # Truncate phases str if too long? "..." was in example.
        # Making it simple: "1: Title; 2: Title"

        current = plan.first_in_progress()
        current_str = f"{current.number}. {current.description}" if current else "None"

        output = (
            f"{header}:\n<task_plan>\nGoal: {plan.objective}\nPhases: {phases_str}\n"
        )

        if previous_phase and next_phase:
            output += f"Previous phase: {previous_phase.number}. {previous_phase.description}\n"
            output += f"Next phase: {next_phase.number}. {next_phase.description}\n"
        else:
            output += f"Current phase: {current_str}\n"

        output += "</task_plan>"
        return output
