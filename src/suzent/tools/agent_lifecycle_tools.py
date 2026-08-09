"""Small, purpose-specific tools for managing sub-agent tasks."""

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

if TYPE_CHECKING:
    from suzent.core.subagent_runner import SubAgentTask


_MAX_TRANSCRIPT_CHARS = 20_000


def _runtime_record(task: "SubAgentTask") -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "parent_chat_id": task.parent_chat_id,
        "chat_id": task.chat_id,
        "description": task.description,
        "status": task.status,
        "result_summary": task.result_summary,
        "error": task.error,
        "model_override": task.model_override,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def _find_accessible_task(
    task_id: str, current_chat_id: str
) -> tuple[dict[str, Any], "SubAgentTask | None"] | None:
    from suzent.core.subagent_runner import get_task

    runtime_task = get_task(task_id)
    if runtime_task and current_chat_id in {
        runtime_task.parent_chat_id,
        runtime_task.chat_id,
    }:
        return _runtime_record(runtime_task), runtime_task

    records = get_database().list_subagent_task_records(task_id=task_id, limit=1)
    if not records:
        return None
    record = records[0]
    if current_chat_id not in {record["parent_chat_id"], record["chat_id"]}:
        return None
    return record, None


def _require_chat_id(ctx: RunContext[AgentDeps]) -> str | None:
    return ctx.deps.chat_id or None


def _format_task(record: dict[str, Any]) -> str:
    title = str(record.get("description") or "Untitled task").replace("\n", " ")
    if len(title) > 100:
        title = title[:97] + "..."
    model = f" · {record['model_override']}" if record.get("model_override") else ""
    return f"- {record['task_id']} · {record['status']}{model}\n  {title}"


def _format_bounded_transcript(
    messages: list[dict[str, str]],
) -> tuple[str, int, bool]:
    """Render recent visible messages without letting one task exhaust context."""
    selected: list[str] = []
    selected_chars = 0
    message_truncated = False
    for message in reversed(messages):
        line = f"[{message['role']}] {message['text']}"
        separator_chars = 1 if selected else 0
        if (
            selected
            and selected_chars + separator_chars + len(line) > _MAX_TRANSCRIPT_CHARS
        ):
            break
        if not selected and len(line) > _MAX_TRANSCRIPT_CHARS:
            line = "[... message truncated ...]\n" + line[-_MAX_TRANSCRIPT_CHARS:]
            message_truncated = True
        selected.append(line)
        selected_chars += separator_chars + len(line)

    selected.reverse()
    omitted = len(messages) - len(selected)
    prefix = f"[... {omitted} earlier messages omitted ...]\n" if omitted else ""
    return prefix + "\n".join(selected), omitted, message_truncated


class AgentListTool(Tool):
    """List active or recent sub-agents owned by the current chat."""

    name = "AgentListTool"
    tool_name = "agent_list"
    group = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        status: Annotated[
            Literal["active", "recent"],
            Field(default="active", description="List active tasks or recent history."),
        ] = "active",
        limit: Annotated[int, Field(default=20, ge=1, le=50)] = 20,
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        if not current_chat_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "No current chat is available."
            )

        from suzent.core.subagent_runner import list_all_tasks

        runtime = list_all_tasks(parent_chat_id=current_chat_id)
        if status == "active":
            records = [
                _runtime_record(task)
                for task in runtime
                if task.status in {"queued", "running"}
            ]
            has_more = len(records) > limit
            records = records[:limit]
        else:
            persisted = get_database().list_subagent_task_records(
                parent_chat_id=current_chat_id, limit=limit + 1
            )
            by_id = {record["task_id"]: record for record in persisted}
            for task in runtime:
                by_id[task.task_id] = _runtime_record(task)
            records = sorted(
                by_id.values(),
                key=lambda record: (
                    record.get("status") in {"queued", "running"},
                    record.get("finished_at") or record.get("started_at") or "",
                ),
                reverse=True,
            )
            has_more = len(records) > limit
            records = records[:limit]

        if not records:
            return ToolResult.success_result(
                f"No {status} sub-agent tasks found.",
                metadata={"tasks": [], "has_more": False},
            )
        return ToolResult.success_result(
            "Sub-agent tasks:\n"
            + "\n".join(_format_task(record) for record in records),
            metadata={"tasks": records, "has_more": has_more},
        )


class AgentReadTool(Tool):
    """Read one sub-agent's status and visible conversation transcript."""

    name = "AgentReadTool"
    tool_name = "agent_read"
    group = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        task_id: Annotated[str, Field(description="Sub-agent task ID.")],
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        found = _find_accessible_task(task_id, current_chat_id or "")
        if not current_chat_id or not found:
            return ToolResult.error_result(
                ToolErrorCode.FILE_NOT_FOUND,
                f"No sub-agent task '{task_id}' is available to this chat.",
            )
        record, _ = found
        chat = get_database().get_chat(record["chat_id"])
        if not chat:
            return ToolResult.error_result(
                ToolErrorCode.FILE_NOT_FOUND,
                f"Sub-agent task '{task_id}' has no persisted conversation.",
            )

        from suzent.database.search import sanitize_messages

        messages = sanitize_messages(chat.messages or [])
        transcript, omitted, message_truncated = _format_bounded_transcript(messages)
        header = f"Sub-agent {task_id} · {record['status']}"
        if record.get("error"):
            header += f"\nError: {record['error']}"
        return ToolResult.success_result(
            f"{header}\n\n{transcript or '(no visible messages)'}",
            metadata={
                **record,
                "message_count": len(messages),
                "omitted_message_count": omitted,
                "transcript_truncated": omitted > 0 or message_truncated,
            },
        )


class AgentWaitTool(Tool):
    """Wait until any selected running sub-agent finishes."""

    name = "AgentWaitTool"
    tool_name = "agent_wait"
    group = ToolGroup.AGENT

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        task_ids: Annotated[
            list[str],
            Field(min_length=1, max_length=8, description="Task IDs to wait for."),
        ],
        timeout_seconds: Annotated[float, Field(default=30, ge=0, le=300)] = 30,
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        if not current_chat_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "No current chat is available."
            )

        runtime_tasks = []
        records = []
        for task_id in dict.fromkeys(task_ids):
            found = _find_accessible_task(task_id, current_chat_id)
            if not found:
                return ToolResult.error_result(
                    ToolErrorCode.FILE_NOT_FOUND,
                    f"No sub-agent task '{task_id}' is available to this chat.",
                )
            record, runtime_task = found
            records.append(record)
            if runtime_task is not None:
                runtime_tasks.append(runtime_task)

        terminal = {"completed", "failed"}
        timed_out = False
        if runtime_tasks and not any(
            record["status"] in terminal for record in records
        ):
            from suzent.core.subagent_runner import wait_for_subagents

            _, timed_out = await wait_for_subagents(
                [task.task_id for task in runtime_tasks], timeout_seconds
            )
            refreshed_records = []
            for task_id, previous_record in zip(
                dict.fromkeys(task_ids), records, strict=True
            ):
                refreshed = _find_accessible_task(task_id, current_chat_id)
                refreshed_records.append(refreshed[0] if refreshed else previous_record)
            records = refreshed_records

        prefix = "Wait timed out; current status:" if timed_out else "Sub-agent status:"
        return ToolResult.success_result(
            prefix + "\n" + "\n".join(_format_task(record) for record in records),
            metadata={"tasks": records, "timed_out": timed_out},
        )


class AgentStopTool(Tool):
    """Stop one running sub-agent owned by the current chat."""

    name = "AgentStopTool"
    tool_name = "agent_stop"
    group = ToolGroup.AGENT

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        task_id: Annotated[str, Field(description="Sub-agent task ID.")],
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        found = _find_accessible_task(task_id, current_chat_id or "")
        if not current_chat_id or not found:
            return ToolResult.error_result(
                ToolErrorCode.FILE_NOT_FOUND,
                f"No sub-agent task '{task_id}' is available to this chat.",
            )
        record, runtime_task = found
        if runtime_task is None or record["status"] not in {"queued", "running"}:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                f"Sub-agent task '{task_id}' is already {record['status']}.",
            )

        from suzent.core.subagent_runner import stop_subagent

        if not await stop_subagent(task_id):
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Failed to stop sub-agent task '{task_id}'.",
            )
        return ToolResult.success_result(
            f"Sub-agent task '{task_id}' stopped.",
            metadata={"task_id": task_id, "status": "failed"},
        )
