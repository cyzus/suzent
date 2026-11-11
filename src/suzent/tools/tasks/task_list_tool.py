from typing import Annotated, Literal, Optional, TypedDict

from pydantic import ConfigDict, Field, with_config
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolGroup, ToolResult
from suzent.tools.tasks.project_scope import require_project_id

logger = get_logger(__name__)


@with_config(ConfigDict(extra="allow", use_attribute_docstrings=True))
class TaskRecord(TypedDict, total=False):
    id: int
    """Pass as task_id to update_task."""
    title: str
    description: str
    status: str
    assignee: Optional[str]
    blocks: list[int]
    blocked_by: list[int]
    active_form: Optional[str]
    waiting_kind: Optional[str]
    waiting_reason: Optional[str]
    next_action: Optional[str]
    result_summary: Optional[str]
    result_path: Optional[str]


@with_config(ConfigDict(extra="allow"))
class TaskListMetadata(TypedDict, total=False):
    count: int
    tasks: list[TaskRecord]


class TaskListResult(ToolResult):
    metadata: TaskListMetadata = Field(default_factory=dict)


class TaskListTool(Tool):
    name: str = "TaskListTool"
    tool_name: str = "list_tasks"
    group: ToolGroup = ToolGroup.TASKS
    # The message already lists the tasks the model reads.
    model_excluded_metadata = frozenset({"tasks"})

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        status: Annotated[
            Optional[
                Literal["pending", "in_progress", "completed", "blocked", "cancelled"]
            ],
            Field(
                description=(
                    "Return only tasks in this status. 'blocked' includes explicit waits "
                    "and pending tasks with dependencies."
                )
            ),
        ] = None,
        assignee: Annotated[
            str | None,
            Field(description="Filter by agent ID or 'main'."),
        ] = None,
        include_completed: Annotated[
            bool,
            Field(description="Include completed tasks, which are omitted by default."),
        ] = False,
        include_cancelled: Annotated[
            bool,
            Field(description="Include cancelled tasks, which are omitted by default."),
        ] = False,
    ) -> TaskListResult:
        project_id, no_project = require_project_id(ctx)
        if no_project:
            return no_project
        db = get_database()
        db_status = None if status == "blocked" else status
        tasks = db.list_tasks(
            project_id=project_id,
            status=db_status,
            assignee=assignee,
            include_completed=include_completed,
            include_cancelled=include_cancelled,
        )
        if status == "blocked":
            tasks = [
                t
                for t in tasks
                if t.status == "blocked" or (t.status == "pending" and t.blocked_by)
            ]
        if not tasks:
            return TaskListResult.success_result(
                "No tasks found.", metadata={"count": 0, "tasks": []}
            )

        lines = ["Tasks:"]
        for task in tasks:
            assignee_str = f" ({task.assignee})" if task.assignee else ""
            blocks_str = (
                f" blocks: {', '.join(f'#{b}' for b in task.blocks)}"
                if task.blocks
                else ""
            )
            blocked_by_str = (
                f" blocked by: {', '.join(f'#{b}' for b in task.blocked_by)}"
                if task.blocked_by
                else ""
            )
            lines.append(
                f"  [#{task.id}] {task.title}{assignee_str} — {task.status}{blocks_str}{blocked_by_str}\n"
                f"    {task.description}\n"
                f"    Progress: {task.active_form or ''}\n"
                f"    Waiting: {task.waiting_kind or ''} {task.waiting_reason or ''}\n"
                f"    Next action: {task.next_action or ''}\n"
                f"    Result: {task.result_summary or ''} {task.result_path or ''}"
            )
        return TaskListResult.success_result(
            "\n".join(lines),
            metadata={
                "count": len(tasks),
                "tasks": [_task_record(task) for task in tasks],
            },
        )


def _task_record(task) -> TaskRecord:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assignee": task.assignee,
        "blocks": list(task.blocks or []),
        "blocked_by": list(task.blocked_by or []),
        "active_form": task.active_form,
        "waiting_kind": task.waiting_kind,
        "waiting_reason": task.waiting_reason,
        "next_action": task.next_action,
        "result_summary": task.result_summary,
        "result_path": task.result_path,
    }
