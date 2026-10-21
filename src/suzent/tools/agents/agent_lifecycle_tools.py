"""Tools for discovering, reading, messaging, and stopping agent sessions."""

import asyncio
from typing import Annotated, Any, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.core.focal_agent import FOCAL_CHAT_ID, is_focal_chat
from suzent.database import ChatModel, get_database
from suzent.a2a import agent_bridge
from suzent.a2a.agent_bridge import A2ABridgeError
from suzent.nodes.agent_transport import (
    PeerAgentTransport,
    PeerAgentTransportError,
    get_peer_agent_transport,
)
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

_MAX_TRANSCRIPT_CHARS = 20_000
_HIDDEN_AGENT_PLATFORMS = {"dream", "subagent_wakeup"}
NEW_AGENT_ID = "new"


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
    if is_focal_chat(current):
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
    if platform == "focal":
        return "focal"
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


def _with_project_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Add the project and bound-task summary the Focal Agent needs across projects."""
    project_id = record.get("project_id")
    if not project_id:
        return record
    db = get_database()
    project = db.get_project(project_id)
    tasks = db.list_tasks(project_id=project_id, chat_id=record["agent_id"])
    return {
        **record,
        "project_slug": project.slug if project else None,
        "project_name": project.name if project else None,
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "waiting_kind": task.waiting_kind,
                "waiting_reason": task.waiting_reason,
            }
            for task in tasks
        ],
    }


def _format_agent(record: dict[str, Any]) -> str:
    title = str(record.get("title") or "Untitled agent").replace("\n", " ")
    if len(title) > 100:
        title = title[:97] + "..."
    line = f"- {record['agent_id']} · {record['kind']} · {record['status']}"
    if record.get("project_slug"):
        line += f" · [{record['project_slug']}]"
    line += f"\n  {title}"
    for task in record.get("tasks") or []:
        line += f"\n  #{task['id']} {task['status']}: {task['title']}"
        if task.get("waiting_reason"):
            line += f" (waiting on {task['waiting_kind']}: {task['waiting_reason']})"
    return line


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
    """List agent sessions, or discover configured ACP agents with status='acp'."""

    name = "AgentListTool"
    tool_name = "agent_list"
    group = ToolGroup.AGENT

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        status: Annotated[
            Literal["active", "recent", "acp"],
            Field(
                description=(
                    "'active' or 'recent': existing sessions to message with agent_send. "
                    "'acp': configured local ACP agents to start with agent(runtime='acp', "
                    "acp_agent_id=...). Checks installation only, not authentication or handshake."
                )
            ),
        ] = "active",
        limit: Annotated[
            int,
            Field(ge=1, le=50, description="Maximum number of agents to return."),
        ] = 20,
    ) -> ToolResult:
        current_chat_id = _require_chat_id(ctx)
        current = get_database().get_chat(current_chat_id) if current_chat_id else None
        if current is None:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "No current agent is available."
            )

        if status == "acp":
            from suzent.acp.registry import ACPAgentRegistry

            configured = ACPAgentRegistry().list_agents()
            records = [
                {
                    "acp_agent_id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "available": agent.available,
                }
                for agent in configured[:limit]
            ]
            lines = [
                f"- {record['acp_agent_id']} · {record['name']} · "
                f"{'installed' if record['available'] else 'not installed'}"
                + (f"\n  {record['description']}" if record["description"] else "")
                for record in records
            ]
            return ToolResult.success_result(
                "Configured ACP agents (installation check only):\n"
                + ("\n".join(lines) or "No ACP agents configured.")
                + "\nStart with agent(runtime='acp', acp_agent_id=<listed ID>, "
                "description=...). These IDs are not agent_send targets. "
                "If not installed, configure it in Settings → ACP Agents.",
                metadata={"acp_agents": records, "has_more": len(configured) > limit},
            )

        focal = is_focal_chat(current)
        if status == "recent":
            if focal:
                summaries = get_database().list_chats(limit=limit + 1)
                chats = [get_database().get_chat(summary.id) for summary in summaries]
            elif current.project_id:
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
        if focal:
            records = [_with_project_summary(record) for record in records]

        # Both federation paths are delegation targets: Suzent peers reached by
        # pairing, and external agents reached by the open A2A protocol.
        remote_records = [
            *get_peer_agent_transport().list_agents(),
            *agent_bridge.list_agents(),
        ]
        if status == "active":
            remote_records = [
                record for record in remote_records if record.get("status") == "ready"
            ]
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

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        agent_id: Annotated[
            str,
            Field(
                description=(
                    "Stable session agent_id from agent_list(active/recent), or the task ID "
                    "returned by agent, including ACP tasks. Sending wakes an idle session. "
                    "Do not pass an acp_agent_id or acp_session_id. The Focal "
                    "Agent may pass 'new' with project_id to start a project session."
                )
            ),
        ],
        message: Annotated[
            str,
            Field(min_length=1, max_length=20_000, description="Message to deliver."),
        ],
        wait: Annotated[
            bool,
            Field(
                description=(
                    "Wait for the agent's reply and get it as this tool's result. "
                    "Otherwise the call returns at once, and a sub-agent's reply "
                    "wakes you when it is ready. Local agents only."
                )
            ),
        ] = False,
        project_id: Annotated[
            Optional[str],
            Field(
                description="Focal Agent only, with agent_id='new': target project ID or slug."
            ),
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
        """Send a message to another agent, such as a sub-agent you spawned.

        A sub-agent keeps its whole history between messages, so use this to
        correct, extend, or question its work rather than spawning a new one.
        """
        current_chat_id = _require_chat_id(ctx)

        if agent_id == NEW_AGENT_ID:
            return self._start_primary_session(
                current_chat_id, message.strip(), project_id, title, task_title
            )

        # SUZENT never parks a turn on another agent: a turn held open would
        # also hold back the wake-ups and session reports queued behind it.
        # Its messages always go out asynchronously and replies wake it later.
        if current_chat_id == FOCAL_CHAT_ID:
            wait = False
            if agent_bridge.parse_address(agent_id):
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    "External agents answer only by blocking until they finish, "
                    "which SUZENT does not do. Ask a project session to delegate "
                    "to this agent instead.",
                )

        # External A2A agents settle in one call — message/send blocks until the
        # remote task completes or asks a question — so the reply comes straight
        # back rather than through the durable outbox the Suzent peer path uses.
        if agent_bridge.parse_address(agent_id):
            try:
                outcome = await asyncio.to_thread(
                    agent_bridge.delegate, agent_id, message.strip()
                )
            except A2ABridgeError as exc:
                return ToolResult.error_result(ToolErrorCode.FILE_NOT_FOUND, str(exc))
            return ToolResult.success_result(
                outcome["summary"],
                metadata={
                    "agent_id": agent_id,
                    "state": outcome["state"],
                    "task_id": outcome.get("task_id"),
                    "transport": "a2a",
                },
            )

        peer_transport = _remote_transport(agent_id)
        if current_chat_id and peer_transport is not None:
            if get_database().get_chat(current_chat_id) is None:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT, "No current agent is available."
                )
            if wait:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    "wait is not supported for remote agents; send without it.",
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

        if wait:
            return await self._send_and_wait(current_chat_id, target, message.strip())

        from suzent.core.agent_inbox import enqueue_agent_message
        from suzent.core.subagent_runner import is_subagent_of

        if current_chat_id == FOCAL_CHAT_ID:
            from suzent.core.focal_agent import watch_session

            watch_session(target.id)
        record, _ = enqueue_agent_message(
            sender_chat_id=current_chat_id,
            target_chat_id=target.id,
            content=message.strip(),
        )
        reply_note = (
            " Its reply will wake you when it is ready."
            if is_subagent_of(target, current_chat_id)
            or current_chat_id == FOCAL_CHAT_ID
            else ""
        )
        return ToolResult.success_result(
            f"Message queued for agent '{target.id}'.{reply_note}",
            metadata={
                "message_id": record["message_id"],
                "agent_id": target.id,
                "status": record["status"],
            },
        )

    @staticmethod
    async def _send_and_wait(
        current_chat_id: str, target: ChatModel, message: str
    ) -> ToolResult:
        from suzent.core.agent_inbox import deliver_and_wait
        from suzent.core.subagent_runner import summarize_agent_output

        try:
            reply = await deliver_and_wait(
                sender_chat_id=current_chat_id,
                target_chat_id=target.id,
                content=message,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Agent '{target.id}' failed to answer: {exc}",
            )
        if reply is None:
            return ToolResult.success_result(
                f"Agent '{target.id}' was already working, so your message joined "
                "its current turn instead of getting a reply of its own.",
                metadata={"agent_id": target.id, "status": "injected"},
            )
        # The reply cites sources only the target's chat knows, so render them
        # as plain references, as a sub-agent's result is.
        text, _ = summarize_agent_output(reply.text, reply.citation_sources, target.id)
        return ToolResult.success_result(
            f"Agent '{target.id}' replied:\n{text}",
            metadata={"agent_id": target.id, "status": "replied"},
        )

    @staticmethod
    def _start_primary_session(
        current_chat_id: Optional[str],
        message: str,
        project_ref: Optional[str],
        title: Optional[str],
        task_title: Optional[str],
    ) -> ToolResult:
        """Start an auto-approving primary session in a project and wake it."""
        db = get_database()
        current = db.get_chat(current_chat_id) if current_chat_id else None
        if not is_focal_chat(current):
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED,
                "Only the Focal Agent can start new project sessions.",
            )
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
                "auto_approve_tools": True,
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
