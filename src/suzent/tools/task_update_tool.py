from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)


class TaskUpdateTool(Tool):
    name: str = "TaskUpdateTool"
    tool_name: str = "update_task"
    group: ToolGroup = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        task_id: Annotated[int, Field(description="ID of the task to update")],
        status: Annotated[
            Optional[Literal["pending", "in_progress", "completed", "cancelled"]],
            Field(default=None),
        ] = None,
        assignee: Annotated[
            Optional[str], Field(default=None, description="Agent ID or 'main'")
        ] = None,
        description: Annotated[
            Optional[str], Field(default=None, description="Replace task description")
        ] = None,
        add_blocks: Annotated[
            Optional[List[int]],
            Field(default=None, description="Additional task IDs this task blocks"),
        ] = None,
        add_blocked_by: Annotated[
            Optional[List[int]],
            Field(default=None, description="Additional task IDs that block this task"),
        ] = None,
    ) -> ToolResult:
        db = get_database()
        task = db.get_task(task_id)
        if not task:
            return ToolResult.error_result(
                ToolErrorCode.NOT_FOUND, f"Task [#{task_id}] not found."
            )

        updates = {}
        if status is not None:
            updates["status"] = status
            if status == "completed":
                updates["completed_at"] = datetime.now(timezone.utc)
            elif status in ("pending", "in_progress"):
                updates["completed_at"] = None
        if assignee is not None:
            updates["assignee"] = assignee
        if description is not None:
            updates["description"] = description
        if add_blocks:
            updates["blocks"] = list(set(task.blocks) | set(add_blocks))
        if add_blocked_by:
            updates["blocked_by"] = list(set(task.blocked_by) | set(add_blocked_by))

        updated = db.update_task(task_id, **updates)
        if not updated:
            return ToolResult.error_result(
                ToolErrorCode.UNKNOWN_ERROR, f"Failed to update task [#{task_id}]."
            )

        msg = f"Task [#{task_id}] updated."
        if status:
            msg += f" Status: {status}."
        if assignee:
            msg += f" Assignee: {assignee}."

        if status == "completed":
            remaining = db.list_tasks(
                project_id=task.project_id,
                include_completed=False,
                include_cancelled=False,
            )
            if not remaining:
                msg += "\n\n**All project tasks completed.** Use manage_goal(action='status') to verify the goal or manage_goal(action='clear') to close it."

        return ToolResult.success_result(msg)
