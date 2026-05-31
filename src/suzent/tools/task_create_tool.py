from typing import Annotated, List, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)


class TaskCreateTool(Tool):
    name: str = "TaskCreateTool"
    tool_name: str = "create_task"
    group: ToolGroup = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        title: Annotated[str, Field(description="Short task title")],
        description: Annotated[str, Field(description="Detailed task description")],
        assignee: Annotated[
            Optional[str],
            Field(default=None, description="Agent ID or 'main' (default)"),
        ] = None,
        blocks: Annotated[
            Optional[List[int]],
            Field(default=None, description="Task IDs this task blocks"),
        ] = None,
        blocked_by: Annotated[
            Optional[List[int]],
            Field(default=None, description="Task IDs that block this task"),
        ] = None,
    ) -> ToolResult:
        project_id = self._resolve_project_id(ctx)
        if not project_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Current chat is not linked to a project.",
            )
        db = get_database()
        task = db.create_task(
            project_id=project_id,
            chat_id=ctx.deps.chat_id,
            title=title,
            description=description,
            assignee=assignee or "main",
            blocks=blocks or [],
            blocked_by=blocked_by or [],
        )
        return ToolResult.success_result(f"Task [#{task.id}] created: {task.title}")

    def _resolve_project_id(self, ctx: RunContext[AgentDeps]) -> Optional[str]:
        chat_id = ctx.deps.chat_id
        if not chat_id:
            return None
        return get_database().get_chat_project_id(chat_id)
