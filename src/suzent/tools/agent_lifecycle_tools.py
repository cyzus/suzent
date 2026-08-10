"""Tools for discovering, reading, messaging, and stopping agent sessions."""

from typing import Annotated, Any, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import ChatModel, get_database
from suzent.nodes.agent_transport import (
    PeerAgentTransport,
    PeerAgentTransportError,
    get_peer_agent_transport,
)
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

_MAX_TRANSCRIPT_CHARS = 20_000
_HIDDEN_AGENT_PLATFORMS = {"dream", "subagent_wakeup"}


def _require_chat_id(ctx: RunContext[AgentDeps]) -> Optional[str]:
    return ctx.deps.chat_id or None


def _remote_transport(agent_id: str) -> Optional[PeerAgentTransport]:
    transport = get_peer_agent_transport()
    return transport if transport.peer_id(agent_id) else None


def _resolve_agent_chat(agent_id: str) -> Optional[ChatModel]:
    """Resolve a stable chat ID, accepting legacy sub-agent task IDs."""
    db = get_database()
    chat = db.get_chat(agent_id)
    if chat is not None:
        return chat
    records = db.list_subagent_task_records(task_id=agent_id, limit=1)
    return db.get_chat(records[0]["chat_id"]) if records else None


def _accessible_agent(agent_id: str, current_chat_id: str) -> Optional[ChatModel]:
    db = get_database()
    current = db.get_chat(current_chat_id)
    target = _resolve_agent_chat(agent_id)
    if current is None or target is None:
        return None
    platform = str((target.config or {}).get("platform") or "").lower()
    if platform in _HIDDEN_AGENT_PLATFORMS:
        return None
    if target.id == current.id:
        return target
    if current.project_id and target.project_id == current.project_id:
        return target
    return None


def _agent_kind(chat: ChatModel) -> str:
    platform = str((chat.config or {}).get("platform") or "").lower()
    if platform == "subagent":
        return "subagent"
    if platform == "cron":
        return "cron"
    if platform == "suzent":
        return "remote"
    if platform in {"social", "telegram", "slack", "discord", "feishu", "wechat"}:
        return "social"
    return "interactive"


def _agent_is_active(chat_id: str) -> bool:
    from suzent.core.run_state import is_running
    from suzent.core.stream_registry import is_background_streaming, stream_controls
    from suzent.core.subagent_runner import list_active_tasks

    control = stream_controls.get(chat_id)
    if control is not None and not control.completed_event.is_set():
        return True
    if is_running(chat_id) or is_background_streaming(chat_id):
        return True
    return any(task.chat_id == chat_id for task in list_active_tasks())


def _agent_record(chat: ChatModel) -> dict[str, Any]:
    config = chat.config or {}
    return {
        "agent_id": chat.id,
        "title": chat.title,
        "kind": _agent_kind(chat),
        "status": "active" if _agent_is_active(chat.id) else "idle",
        "project_id": chat.project_id,
        "parent_agent_id": config.get("parent_chat_id"),
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }


def _format_agent(record: dict[str, Any]) -> str:
    title = str(record.get("title") or "Untitled agent").replace("\n", " ")
    if len(title) > 100:
        title = title[:97] + "..."
    return f"- {record['agent_id']} · {record['kind']} · {record['status']}\n  {title}"


def _format_bounded_transcript(
    messages: list[dict[str, str]],
) -> tuple[str, int, bool]:
    """Render recent visible messages without letting one agent exhaust context."""
    from suzent.database.search import bound_message_records

    selected, omitted, message_truncated = bound_message_records(
        messages, _MAX_TRANSCRIPT_CHARS
    )
    prefix = f"[... {omitted} earlier messages omitted ...]\n" if omitted else ""
    lines = [f"[{message['role']}] {message['text']}" for message in selected]
    return prefix + "\n".join(lines), omitted, message_truncated


class AgentListTool(Tool):
    """List local project agents and paired remote Suzent agents."""

    name = "AgentListTool"
    tool_name = "agent_list"
    group = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        status: Annotated[
            Literal["active", "recent"],
            Field(default="active", description="List active agents or recent agents."),
        ] = "active",
        limit: Annotated[int, Field(default=20, ge=1, le=50)] = 20,
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        current = get_database().get_chat(current_chat_id) if current_chat_id else None
        if current is None:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "No current agent is available."
            )

        if status == "recent":
            if current.project_id:
                summaries = get_database().list_chats(
                    limit=limit + 1, project_id=current.project_id
                )
                chats = [get_database().get_chat(summary.id) for summary in summaries]
            else:
                chats = [current]
            records = [
                _agent_record(chat)
                for chat in chats
                if chat is not None
                and str((chat.config or {}).get("platform") or "").lower()
                not in _HIDDEN_AGENT_PLATFORMS
            ]
        else:
            from suzent.core.stream_registry import (
                active_stream_queues,
                background_queues,
                stream_controls,
            )
            from suzent.core.subagent_runner import list_active_tasks

            active_ids = {
                *active_stream_queues,
                *background_queues,
                *stream_controls,
                *(task.chat_id for task in list_active_tasks()),
            }
            chats = [_accessible_agent(agent_id, current.id) for agent_id in active_ids]
            records = [
                _agent_record(chat)
                for chat in chats
                if chat is not None and _agent_is_active(chat.id)
            ]
            records.sort(key=lambda item: item.get("updated_at") or "", reverse=True)

        remote_records = get_peer_agent_transport().list_agents()
        records = [*remote_records, *records]

        has_more = len(records) > limit
        records = records[:limit]
        if not records:
            return ToolResult.success_result(
                f"No {status} local or paired remote agents found.",
                metadata={"agents": [], "has_more": False},
            )
        return ToolResult.success_result(
            "Agents:\n" + "\n".join(_format_agent(record) for record in records),
            metadata={"agents": records, "has_more": has_more},
        )


class AgentReadTool(Tool):
    """Read one accessible agent's bounded visible transcript."""

    name = "AgentReadTool"
    tool_name = "agent_read"
    group = ToolGroup.AGENT

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        agent_id: Annotated[str, Field(description="Stable agent ID from agent_list.")],
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        peer_transport = _remote_transport(agent_id)
        if current_chat_id and peer_transport is not None:
            if get_database().get_chat(current_chat_id) is None:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT, "No current agent is available."
                )
            try:
                remote = await peer_transport.read(agent_id)
            except PeerAgentTransportError as exc:
                return ToolResult.error_result(ToolErrorCode.EXECUTION_FAILED, str(exc))
            messages = remote.get("messages") or []
            transcript, omitted, message_truncated = _format_bounded_transcript(
                messages
            )
            remote_omitted = int(remote.get("omitted_message_count") or 0)
            if remote_omitted:
                transcript = (
                    f"[... {remote_omitted} earlier messages omitted ...]\n{transcript}"
                )
            return ToolResult.success_result(
                f"Agent {agent_id} · remote · {remote.get('status', 'idle')}\n\n"
                f"{transcript or '(no visible messages)'}",
                metadata={
                    "agent_id": agent_id,
                    "kind": "remote",
                    "status": remote.get("status", "idle"),
                    "message_count": remote.get("message_count", len(messages)),
                    "omitted_message_count": remote.get(
                        "omitted_message_count", omitted
                    ),
                    "transcript_truncated": remote.get(
                        "transcript_truncated", omitted > 0 or message_truncated
                    ),
                },
            )

        target = _accessible_agent(agent_id, current_chat_id or "")
        if current_chat_id is None or target is None:
            return ToolResult.error_result(
                ToolErrorCode.FILE_NOT_FOUND,
                f"Agent '{agent_id}' is not available in the current project.",
            )

        from suzent.database.search import sanitize_messages

        messages = sanitize_messages(target.messages or [])
        transcript, omitted, message_truncated = _format_bounded_transcript(messages)
        record = _agent_record(target)
        return ToolResult.success_result(
            f"Agent {target.id} · {record['kind']} · {record['status']}\n\n"
            f"{transcript or '(no visible messages)'}",
            metadata={
                **record,
                "message_count": len(messages),
                "omitted_message_count": omitted,
                "transcript_truncated": omitted > 0 or message_truncated,
            },
        )


class AgentSendTool(Tool):
    """Durably send a message to another accessible agent and wake it."""

    name = "AgentSendTool"
    tool_name = "agent_send"
    group = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        agent_id: Annotated[str, Field(description="Stable agent ID from agent_list.")],
        message: Annotated[
            str,
            Field(min_length=1, max_length=20_000, description="Message to deliver."),
        ],
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        peer_transport = _remote_transport(agent_id)
        if current_chat_id and peer_transport is not None:
            if get_database().get_chat(current_chat_id) is None:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT, "No current agent is available."
                )
            try:
                record, _ = peer_transport.enqueue(
                    agent_id=agent_id,
                    sender_chat_id=current_chat_id,
                    content=message.strip(),
                )
            except PeerAgentTransportError as exc:
                return ToolResult.error_result(ToolErrorCode.FILE_NOT_FOUND, str(exc))
            return ToolResult.success_result(
                f"Message queued for remote agent '{agent_id}'.",
                metadata={
                    "message_id": record["message_id"],
                    "agent_id": agent_id,
                    "status": record["status"],
                    "transport": "suzent_peer",
                },
            )

        target = _accessible_agent(agent_id, current_chat_id or "")
        if current_chat_id is None or target is None:
            return ToolResult.error_result(
                ToolErrorCode.FILE_NOT_FOUND,
                f"Agent '{agent_id}' is not available in the current project.",
            )
        if target.id == current_chat_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Use a normal follow-up turn instead of sending to the current agent.",
            )

        from suzent.core.agent_inbox import enqueue_agent_message

        record, _ = enqueue_agent_message(
            sender_chat_id=current_chat_id,
            target_chat_id=target.id,
            content=message.strip(),
        )
        return ToolResult.success_result(
            f"Message queued for agent '{target.id}'.",
            metadata={
                "message_id": record["message_id"],
                "agent_id": target.id,
                "status": record["status"],
            },
        )


class AgentStopTool(Tool):
    """Stop an active local or paired remote agent session."""

    name = "AgentStopTool"
    tool_name = "agent_stop"
    group = ToolGroup.AGENT

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        agent_id: Annotated[str, Field(description="Stable agent ID from agent_list.")],
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        peer_transport = _remote_transport(agent_id)
        if current_chat_id and peer_transport is not None:
            if get_database().get_chat(current_chat_id) is None:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT, "No current agent is available."
                )
            try:
                stopped = await peer_transport.stop(agent_id)
            except PeerAgentTransportError as exc:
                return ToolResult.error_result(ToolErrorCode.EXECUTION_FAILED, str(exc))
            if not stopped:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"Remote agent '{agent_id}' is not active.",
                )
            return ToolResult.success_result(
                f"Remote agent '{agent_id}' stopped.",
                metadata={"agent_id": agent_id, "status": "stopping"},
            )

        target = _accessible_agent(agent_id, current_chat_id or "")
        if current_chat_id is None or target is None:
            return ToolResult.error_result(
                ToolErrorCode.FILE_NOT_FOUND,
                f"Agent '{agent_id}' is not available in the current project.",
            )
        if target.id == current_chat_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "The current agent cannot stop itself with agent_stop.",
            )
        if not _agent_is_active(target.id):
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, f"Agent '{target.id}' is not active."
            )

        from suzent.core.stream_registry import stop_stream
        from suzent.core.subagent_runner import list_active_tasks, stop_subagent

        subagent_task = next(
            (task for task in list_active_tasks() if task.chat_id == target.id), None
        )
        stopped = (
            await stop_subagent(subagent_task.task_id)
            if subagent_task is not None
            else stop_stream(target.id, reason="Agent stopped by another agent")
        )
        if not stopped:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Failed to stop agent '{target.id}'.",
            )
        return ToolResult.success_result(
            f"Agent '{target.id}' stopped.",
            metadata={"agent_id": target.id, "status": "stopping"},
        )
