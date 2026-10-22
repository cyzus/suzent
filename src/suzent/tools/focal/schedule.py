"""Regent's wake-ups: reminders for the user and quiet checks on work."""

from typing import Annotated, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import ToolErrorCode, ToolResult
from suzent.tools.schedule_tool import (
    MIN_INTERVAL_MINUTES,
    ScheduleAction,
    ScheduleTool,
)


class FocalScheduleTool(ScheduleTool):
    """Schedule when you wake next: a reminder for the user, or a quiet check.

    Always runs in the Focal conversation, under its own tools; there is no
    isolated variant, which would run with a full tool set. Only Regent is
    equipped with it, and it refuses any other chat.
    """

    name: str = "FocalScheduleTool"
    display_name: Optional[str] = "Schedule wake-ups"
    tool_name: str = "schedule_wakeup"
    # Not user-configurable and not discoverable through ToolSearch: Focal only.
    group = ""
    deferrable = False
    max_tasks_per_chat: int = 20

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        action: Annotated[
            ScheduleAction,
            Field(
                description=(
                    "'create' a wake-up, 'list' them, 'update' one, or 'cancel' one."
                )
            ),
        ] = "list",
        kind: Annotated[
            Literal["reminder", "check"],
            Field(
                description=(
                    "'reminder': something the user asked to be told; always "
                    "notifies them. 'check': look in on work yourself; the user "
                    "is notified only if you find something worth saying."
                )
            ),
        ] = "check",
        name: Annotated[
            Optional[str],
            Field(description="Short label, e.g. 'stand-up reminder'."),
        ] = None,
        prompt: Annotated[
            Optional[str],
            Field(
                description=("What to do when it fires, written for your future self.")
            ),
        ] = None,
        in_minutes: Annotated[
            Optional[int],
            Field(description="Once, this many minutes from now."),
        ] = None,
        at: Annotated[
            Optional[str],
            Field(description="Once, at this ISO 8601 local timestamp."),
        ] = None,
        every_minutes: Annotated[
            Optional[int],
            Field(description=f"Repeat every N minutes (min {MIN_INTERVAL_MINUTES})."),
        ] = None,
        cron: Annotated[
            Optional[str],
            Field(description="Repeat on a 5-field cron expression."),
        ] = None,
        timezone: Annotated[
            Optional[str],
            Field(description="IANA timezone for a cron schedule."),
        ] = None,
        task_id: Annotated[
            Optional[int],
            Field(description="Wake-up to act on, for 'update' and 'cancel'."),
        ] = None,
    ) -> ToolResult:
        from suzent.core.focal_agent import is_focal_chat_id

        chat_id = ctx.deps.chat_id
        if not is_focal_chat_id(chat_id):
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED,
                "schedule_wakeup belongs to Regent; use schedule_task.",
            )
        action = (action or "list").strip().lower()
        if action == "list":
            return self._list(chat_id)
        if action == "cancel":
            return self._cancel(chat_id, task_id)
        if action == "update":
            return self._update(chat_id, task_id, every_minutes, cron, prompt, name)
        if action == "create":
            reminder = kind == "reminder"
            return self._create(
                chat_id=chat_id,
                name=name,
                prompt=prompt,
                in_minutes=in_minutes,
                at=at,
                every_minutes=every_minutes,
                cron=cron,
                timezone=timezone,
                bind_to_chat=True,
                quiet_if_nothing_to_report=not reminder,
                announce=reminder,
            )
        return ToolResult.error_result(
            ToolErrorCode.INVALID_ARGUMENT,
            f"Unknown action {action!r}. Use create, list, update or cancel.",
        )
