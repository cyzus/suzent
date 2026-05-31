from typing import Annotated, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)


class TaskListTool(Tool):
    name: str = "TaskListTool"
    tool_name: str = "list_tasks"
    group: ToolGroup = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        status: Annotated[
            Optional[
                Literal["pending", "in_progress", "completed", "blocked", "cancelled"]
            ],
            Field(default=None),
        ] = None,
        assignee: Annotated[
            Optional[str],
            Field(default=None, description="Filter by agent ID or 'main'"),
        ] = None,
        include_completed: Annotated[bool, Field(default=False)] = False,
        include_cancelled: Annotated[bool, Field(default=False)] = False,
    ) -> ToolResult:
        project_id = self._resolve_project_id(ctx)
        if not project_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Current chat is not linked to a project.",
            )
        db = get_database()
        tasks = db.list_tasks(
            project_id=project_id,
            chat_id=ctx.deps.chat_id,
            status=status,
            assignee=assignee,
            include_completed=include_completed,
            include_cancelled=include_cancelled,
        )
        if not tasks:
            return ToolResult.success_result("No tasks found.")

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
                f"    {task.description}"
            )
        return ToolResult.success_result("\n".join(lines))

    def _resolve_project_id(self, ctx: RunContext[AgentDeps]) -> Optional[str]:
        chat_id = ctx.deps.chat_id
        if not chat_id:
            return None
        return get_database().get_chat_project_id(chat_id)
