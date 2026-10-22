"""SUZENT's dispatch: send work to project sessions, or start new ones."""

from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.a2a import agent_bridge
from suzent.core.agent_deps import AgentDeps
from suzent.core.focal_agent import FOCAL_CHAT_ID, is_focal_chat
from suzent.database import get_database
from suzent.tools.agents.agent_lifecycle_tools import (
    NEW_AGENT_ID,
    AgentSendTool,
    _require_chat_id,
)
from suzent.tools.base import ToolErrorCode, ToolResult


class FocalDispatchTool(AgentSendTool):
    """Send work to a project session, or start a new session in a project.

    Only SUZENT is equipped with it, and it refuses any other chat. Messages
    always go out asynchronously, and replies wake you later.
    """

    name = "FocalDispatchTool"
    display_name = "Dispatch to sessions"
    tool_name = "agent_dispatch"
    # Not user-configurable and not discoverable through ToolSearch: Focal only.
    group = ""
    deferrable = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        agent_id: Annotated[
            str,
            Field(
                description=(
                    "Session ID from agent_list, or 'new' with project_id to start "
                    "a session in that project."
                )
            ),
        ],
        message: Annotated[
            str,
            Field(min_length=1, max_length=20_000, description="Message to deliver."),
        ],
        project_id: Annotated[
            Optional[str],
            Field(description="With agent_id='new': target project ID or slug."),
        ] = None,
        title: Annotated[
            Optional[str],
            Field(description="With agent_id='new': title of the new session."),
        ] = None,
        task_title: Annotated[
            Optional[str],
            Field(
                description="With agent_id='new': create a task bound to the new session."
            ),
        ] = None,
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        if not is_focal_chat(get_database().get_chat(current_chat_id)):
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED,
                "agent_dispatch belongs to SUZENT; use agent_send.",
            )
        if agent_id == NEW_AGENT_ID:
            return self._start_primary_session(
                current_chat_id, message.strip(), project_id, title, task_title
            )
        # SUZENT never parks a turn on another agent: a turn held open would
        # also hold back the wake-ups and session reports queued behind it.
        if agent_bridge.parse_address(agent_id):
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "External agents answer only by blocking until they finish, "
                "which SUZENT does not do. Ask a project session to delegate "
                "to this agent instead.",
            )
        return await self._deliver(current_chat_id, agent_id, message.strip(), False)

    @staticmethod
    def _start_primary_session(
        current_chat_id: str,
        message: str,
        project_ref: Optional[str],
        title: Optional[str],
        task_title: Optional[str],
    ) -> ToolResult:
        """Start a Smart-mode primary session in a project and wake it."""
        db = get_database()
        current = db.get_chat(current_chat_id)
        if not project_ref:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "project_id is required when agent_id is 'new'.",
            )
        project = db.get_project(project_ref) or db.get_project_by_slug(project_ref)
        if project is None or project.archived:
            return ToolResult.error_result(
                ToolErrorCode.NOT_FOUND, f"Project '{project_ref}' not found."
            )

        task_title = (task_title or "").strip()
        new_chat_id = db.create_chat(
            title=(title or "").strip() or task_title or message[:60],
            config={
                "permission_mode": "auto",
                "parent_chat_id": current.id,
                "spawned_by_focal": current.id == FOCAL_CHAT_ID,
            },
            project_id=project.id,
        )
        task = (
            db.create_task(
                project_id=project.id,
                chat_id=new_chat_id,
                title=task_title,
                description=message,
                status="in_progress",
                assignee=new_chat_id,
            )
            if task_title
            else None
        )

        from suzent.core.agent_inbox import enqueue_agent_message

        record, _ = enqueue_agent_message(
            sender_chat_id=current.id,
            target_chat_id=new_chat_id,
            content=message,
        )
        summary = f"Started session '{new_chat_id}' in project '{project.slug}'."
        if task is not None:
            summary += f" Bound task [#{task.id}]."
        return ToolResult.success_result(
            summary,
            metadata={
                "message_id": record["message_id"],
                "agent_id": new_chat_id,
                "project_id": project.id,
                "project_slug": project.slug,
                "task_id": task.id if task is not None else None,
                "status": record["status"],
            },
        )
