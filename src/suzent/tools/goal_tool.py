from typing import Annotated, Optional, Literal

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)

DEFAULT_MAX_TURNS = 20


class GoalTool(Tool):
    name: str = "GoalTool"
    tool_name: str = "manage_goal"
    group: ToolGroup = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        action: Annotated[
            Literal["set", "pause", "resume", "clear", "status", "subgoal"],
            Field(
                description="set: set goal; pause: pause tracking; resume: resume tracking; clear: mark goal done; status: view current goal; subgoal: add/remove a subgoal"
            ),
        ],
        objective: Annotated[
            Optional[str],
            Field(
                default=None, description="Goal description (required for action='set')"
            ),
        ] = None,
        subgoal_text: Annotated[
            Optional[str],
            Field(default=None, description="Subgoal text to add (action='subgoal')"),
        ] = None,
        subgoal_index: Annotated[
            Optional[int],
            Field(
                default=None,
                description="Index of subgoal to remove (action='subgoal')",
            ),
        ] = None,
        max_turns: Annotated[
            Optional[int],
            Field(
                default=None,
                ge=1,
                description="Max Ralph Loop turns (action='set', optional)",
            ),
        ] = None,
    ) -> ToolResult:
        project_id = self._resolve_project_id(ctx)
        if not project_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Current chat is not linked to a project.",
            )

        chat_id = ctx.deps.chat_id
        if action == "set":
            return self._set_goal(project_id, objective, max_turns, chat_id=chat_id)
        elif action == "pause":
            return self._change_status(project_id, "paused", chat_id=chat_id)
        elif action == "resume":
            return self._change_status(project_id, "active", chat_id=chat_id)
        elif action == "clear":
            return self._clear_goal(project_id, chat_id=chat_id)
        elif action == "status":
            return self._get_status(project_id, chat_id=chat_id)
        elif action == "subgoal":
            return self._manage_subgoal(
                project_id, subgoal_text, subgoal_index, chat_id=chat_id
            )
        else:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, f"Unknown action: {action}"
            )

    def _resolve_project_id(self, ctx: RunContext[AgentDeps]) -> Optional[str]:
        chat_id = ctx.deps.chat_id
        if not chat_id:
            return None
        return get_database().get_chat_project_id(chat_id)

    def _set_goal(
        self,
        project_id: str,
        objective: Optional[str],
        max_turns: Optional[int],
        chat_id: Optional[str] = None,
    ) -> ToolResult:
        if not objective:
            return ToolResult.error_result(
                ToolErrorCode.MISSING_REQUIRED_PARAM,
                "objective is required for action='set'",
            )
        db = get_database()
        goal = db.get_goal(project_id, chat_id=chat_id)
        effective_turns = max_turns or DEFAULT_MAX_TURNS
        if goal:
            db.update_goal(
                goal.id,
                objective=objective,
                status="active",
                turns_elapsed=0,
                max_turns=effective_turns,
            )
        else:
            db.create_goal(
                project_id, objective, chat_id=chat_id, max_turns=effective_turns
            )
        return ToolResult.success_result(f"Goal set: {objective}")

    def _change_status(
        self, project_id: str, status: str, chat_id: Optional[str] = None
    ) -> ToolResult:
        db = get_database()
        goal = db.get_goal(project_id, chat_id=chat_id)
        if not goal:
            return ToolResult.error_result(
                ToolErrorCode.NOT_FOUND, "No active goal found."
            )
        db.update_goal(goal.id, status=status)
        return ToolResult.success_result(f"Goal status changed to: {status}")

    def _clear_goal(self, project_id: str, chat_id: Optional[str] = None) -> ToolResult:
        db = get_database()
        if not db.get_goal(project_id, chat_id=chat_id):
            return ToolResult.success_result("No active goal to clear.")
        db.clear_goal(project_id, chat_id=chat_id)
        return ToolResult.success_result("Goal marked as completed.")

    def _get_status(self, project_id: str, chat_id: Optional[str] = None) -> ToolResult:
        db = get_database()
        goal = db.get_goal(project_id, chat_id=chat_id)
        if not goal:
            return ToolResult.success_result("No active goal.")
        turns_info = ""
        if goal.max_turns:
            remaining = goal.max_turns - goal.turns_elapsed
            turns_info = f"\nTurns: {goal.turns_elapsed}/{goal.max_turns} ({remaining} remaining)"
        subgoals_str = ""
        if goal.subgoals:
            subgoals_str = "\nSubgoals:\n" + "\n".join(
                f"  [{i}] {sg}" for i, sg in enumerate(goal.subgoals)
            )
        return ToolResult.success_result(
            f"Goal: {goal.objective}\nStatus: {goal.status}{turns_info}{subgoals_str}"
        )

    def _manage_subgoal(
        self,
        project_id: str,
        subgoal_text: Optional[str],
        subgoal_index: Optional[int],
        chat_id: Optional[str] = None,
    ) -> ToolResult:
        db = get_database()
        goal = db.get_goal(project_id, chat_id=chat_id)
        if not goal:
            return ToolResult.error_result(
                ToolErrorCode.NOT_FOUND, "No active goal to manage subgoals on."
            )
        subgoals = list(goal.subgoals)
        if subgoal_index is not None:
            if 0 <= subgoal_index < len(subgoals):
                removed = subgoals.pop(subgoal_index)
                db.update_goal(goal.id, subgoals=subgoals)
                return ToolResult.success_result(f"Removed subgoal: {removed}")
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                f"Subgoal index {subgoal_index} out of range.",
            )
        if subgoal_text:
            subgoals.append(subgoal_text)
            db.update_goal(goal.id, subgoals=subgoals)
            return ToolResult.success_result(f"Added subgoal: {subgoal_text}")
        return ToolResult.error_result(
            ToolErrorCode.MISSING_REQUIRED_PARAM,
            "Provide subgoal_text (add) or subgoal_index (remove).",
        )
