"""Small, purpose-specific tools for managing sub-agent tasks."""

from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult


def _runtime_record(task) -> dict:
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
) -> tuple[dict, object | None] | None:
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


def _format_task(record: dict) -> str:
    title = str(record.get("description") or "Untitled task").replace("\n", " ")
    if len(title) > 100:
        title = title[:97] + "..."
    model = f" · {record['model_override']}" if record.get("model_override") else ""
    return f"- {record['task_id']} · {record['status']}{model}\n  {title}"


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
        transcript = "\n".join(
            f"[{message['role']}] {message['text']}" for message in messages
        )
        header = f"Sub-agent {task_id} · {record['status']}"
        if record.get("error"):
            header += f"\nError: {record['error']}"
        return ToolResult.success_result(
            f"{header}\n\n{transcript or '(no visible messages)'}",
            metadata={**record, "message_count": len(messages)},
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
        if runtime_tasks and not any(task.status in terminal for task in runtime_tasks):
            from suzent.core.subagent_runner import wait_for_subagents

            _, timed_out = await wait_for_subagents(
                [task.task_id for task in runtime_tasks], timeout_seconds
            )
            records = [
                _find_accessible_task(task_id, current_chat_id)[0]
                for task_id in dict.fromkeys(task_ids)
            ]

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
