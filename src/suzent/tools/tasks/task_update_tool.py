from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.core.focal_agent import (
    ATTENTION_WAITING_KINDS,
    notify_focal_of_blocked_task,
    notify_focal_of_finished_session,
)
from suzent.core.project_context import resolve_project_id
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)


class TaskUpdateTool(Tool):
    name: str = "TaskUpdateTool"
    tool_name: str = "update_task"
    group: ToolGroup = ToolGroup.TASKS

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        task_id: Annotated[int, Field(description="ID of the task to update")],
        status: Annotated[
            Optional[
                Literal["pending", "in_progress", "blocked", "completed", "cancelled"]
            ],
            Field(
                description=(
                    "New status. Setting 'completed' stamps completed_at; any "
                    "other value clears it. Use blocked when execution cannot continue, "
                    "and provide waiting_kind, waiting_reason and next_action. "
                    "On completion, provide result_summary and result_path if a file was produced."
                )
            ),
        ] = None,
        assignee: Annotated[
            Optional[str], Field(description="Agent ID or 'main'")
        ] = None,
        description: Annotated[
            Optional[str], Field(description="Replace task description")
        ] = None,
        add_blocks: Annotated[
            Optional[List[int]],
            Field(description="Additional task IDs this task blocks"),
        ] = None,
        add_blocked_by: Annotated[
            Optional[List[int]],
            Field(description="Additional task IDs that block this task"),
        ] = None,
        active_form: Annotated[
            str | None, Field(description="Current progress, in plain language")
        ] = None,
        waiting_kind: Annotated[
            Literal["user", "dependency", "paused", "error"] | None,
            Field(
                description="Why blocked: user input, dependency, explicit pause, or failed recovery"
            ),
        ] = None,
        waiting_reason: Annotated[
            str | None, Field(description="Explain what prevents progress")
        ] = None,
        next_action: Annotated[
            str | None, Field(description="Concrete action needed to continue")
        ] = None,
        result_summary: Annotated[
            str | None, Field(description="Completed outcome and validation summary")
        ] = None,
        result_path: Annotated[
            str | None,
            Field(description="Path to the output file in this chat's workspace"),
        ] = None,
    ) -> ToolResult:
        db = get_database()
        task = db.get_task(task_id)
        if not task:
            return ToolResult.error_result(
                ToolErrorCode.NOT_FOUND, f"Task [#{task_id}] not found."
            )

        project_id = resolve_project_id(ctx.deps.chat_id)
        if not project_id or task.project_id != project_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                f"Task [#{task_id}] does not belong to the current project.",
            )

        updates = {}
        if not task.chat_id:
            updates["chat_id"] = ctx.deps.chat_id
        for key, value in {
            "active_form": active_form,
            "waiting_kind": waiting_kind,
            "waiting_reason": waiting_reason,
            "next_action": next_action,
            "result_summary": result_summary,
            "result_path": result_path,
        }.items():
            if value is not None:
                updates[key] = value
        if status is not None:
            updates["status"] = status
            if status == "completed":
                updates["completed_at"] = datetime.now(timezone.utc)
            else:
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

        newly_needs_user = (
            updated.status == "blocked"
            and updated.waiting_kind in ATTENTION_WAITING_KINDS
            and (
                task.status != "blocked"
                or task.waiting_kind != updated.waiting_kind
                or task.waiting_reason != updated.waiting_reason
            )
        )
        if newly_needs_user:
            notify_focal_of_blocked_task(updated, updated.chat_id or ctx.deps.chat_id)
        closed = ("completed", "cancelled")
        if updated.chat_id and updated.status in closed and task.status not in closed:
            notify_focal_of_finished_session(updated.chat_id)

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
