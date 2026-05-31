from typing import Annotated, List, Optional

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)


class TaskInput(BaseModel):
    title: str = Field(description="Short task title")
    description: str = Field(description="Detailed task description")
    assignee: Optional[str] = Field(
        default=None, description="Agent ID or 'main' (default)"
    )
    blocks: Optional[List[int]] = Field(
        default=None, description="Task IDs this task blocks"
    )
    blocked_by: Optional[List[int]] = Field(
        default=None, description="Task IDs that block this task"
    )


class TaskCreateTool(Tool):
    name: str = "TaskCreateTool"
    tool_name: str = "create_tasks"
    group: ToolGroup = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        tasks: Annotated[
            List[TaskInput],
            Field(
                description="List of tasks to create. Each task has title, description, and optional assignee/blocks/blocked_by."
            ),
        ],
    ) -> ToolResult:
        project_id = self._resolve_project_id(ctx)
        if not project_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Current chat is not linked to a project.",
            )
        if not tasks:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "tasks list cannot be empty.",
            )

        db = get_database()
        created = []
        for t in tasks:
            task = db.create_task(
                project_id=project_id,
                chat_id=ctx.deps.chat_id,
                title=t.title,
                description=t.description,
                assignee=t.assignee or "main",
                blocks=t.blocks or [],
                blocked_by=t.blocked_by or [],
            )
            created.append(f"[#{task.id}] {task.title}")

        lines = "\n".join(f"  {c}" for c in created)
        return ToolResult.success_result(f"Created {len(created)} task(s):\n{lines}")

    def _resolve_project_id(self, ctx: RunContext[AgentDeps]) -> Optional[str]:
        chat_id = ctx.deps.chat_id
        if not chat_id:
            return None
        return get_database().get_chat_project_id(chat_id)
