"""Lifecycle manager for ACP subprocesses and resumable sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from suzent.logger import get_logger

from .client import ACPClient, ACPError
from .permissions import PERMISSION_QUEUE_KEY, get_permission_broker
from .registry import ACPAgentRegistry


def default_acp_cwd(chat_id: str) -> str:
    """Where an ACP session starts when the caller names no cwd.

    The chat's working directory (its own, else its project's setting), else
    the chat's project directory.
    """
    from suzent.database import get_database

    database = get_database()
    working_directory = database.resolve_chat_working_directory(
        database.get_chat(chat_id)
    )
    return working_directory or _resolve_project_dir(chat_id)


def _resolve_project_dir(chat_id: str) -> str:
    """Return the sandbox project directory for *chat_id*.

    Mirrors the fallback the Bash tool uses when ``deps.cwd`` is unset:
    ``{sandbox_data_path}/projects/{project_slug}``.
    """
    from suzent.config import CONFIG
    from suzent.database import get_database

    sandbox_data_path = Path(CONFIG.sandbox_data_path).resolve()
    project_slug = get_database().get_chat_project_slug(chat_id)
    project_dir = sandbox_data_path / "projects" / project_slug
    project_dir.mkdir(parents=True, exist_ok=True)
    return str(project_dir)


logger = get_logger(__name__)


@dataclass
class ManagedSession:
    chat_id: str
    agent_id: str
    session_id: str
    cwd: str
    client: ACPClient
    updates: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    capabilities: dict[str, Any] = field(default_factory=dict)
    agent_info: dict[str, Any] = field(default_factory=dict)
    protocol_version: Any = None
    # True when this session carries the history that was asked for -- either
    # session/load succeeded, or it is the same live session as before.
    resumed: bool = False
    # True while this session came from session/load on a freshly spawned
    # process and has not yet proven it can actually run a turn. Agents may
    # accept a session id their process no longer has, which only shows up as a
    # failed turn; cleared once a turn produces output.
    restored: bool = False
    # Chat permission_mode; 'auto'/'full_access' skip the approval prompt.
    permission_mode: str = ""
    # Why session/load failed, when a resume fell back to a fresh session.
    load_error: str = ""


class ACPManager:
    def __init__(self, registry: ACPAgentRegistry | None = None):
        self.registry = registry or ACPAgentRegistry()
        self._sessions: dict[str, ManagedSession] = {}
        self._lock = asyncio.Lock()
        self._authenticated: dict[str, tuple[ACPClient, dict[str, Any]]] = {}
        from .authentication import ACPLogins

        self.logins = ACPLogins(self)

    def list_active(self) -> list[dict[str, Any]]:
        return [
            {
                "chat_id": item.chat_id,
                "agent_id": item.agent_id,
                "session_id": item.session_id,
                "cwd": item.cwd,
            }
            for item in self._sessions.values()
        ]

    async def probe(
        self, agent_id: str, cwd: str, method_id: str | None = None
    ) -> dict[str, Any]:
        """Check session readiness, optionally performing a user-selected login."""
        agent = self.registry.get(agent_id)
        if not agent.available:
            raise ValueError("Agent binary not found or unavailable")
        cached = self._authenticated.pop(agent_id, None) if method_id is None else None
        if cached and not cached[0].is_running:
            await cached[0].close()
            cached = None
        client = (
            cached[0]
            if cached
            else ACPClient(agent.command, cwd=agent.cwd or cwd, env=agent.env)
        )
        retained = False
        try:
            from .terminal_login import terminal_available

            client.terminal_auth = terminal_available()
            if cached:
                init = cached[1]
            else:
                await client.start()
                init = await client.initialize()
            methods = [
                method
                for method in (init.get("authMethods") or [])
                if isinstance(method, dict) and isinstance(method.get("id"), str)
            ]
            if method_id is not None:
                selected = next((m for m in methods if m["id"] == method_id), None)
                if selected is None:
                    raise ValueError(
                        "Authentication method was not advertised by this agent"
                    )
                if selected.get("type", "agent") != "agent":
                    raise ValueError(
                        "This authentication method requires external login"
                    )
                await client.authenticate(method_id)
            status = "ready"
            if (
                agent.id == "claude-code"
                and "suzent.acp.claude_bridge" in agent.command
            ):
                from .authentication import claude_authenticated

                if not await claude_authenticated(agent.cwd or cwd, agent.env):
                    return {
                        "status": "auth_required",
                        "authMethods": [],
                        "protocolVersion": init.get("protocolVersion"),
                    }
            try:
                await client.new_session(cwd)
            except ACPError as exc:
                if not exc.auth_required:
                    raise
                status = "auth_required"
            if (method_id is not None or cached) and status == "ready":
                previous = self._authenticated.pop(agent_id, None)
                self._authenticated[agent_id] = (client, init)
                retained = True
                if previous is not None:
                    await previous[0].close()
            return {
                "protocolVersion": init.get("protocolVersion"),
                "agentInfo": init.get("agentInfo", {}),
                "capabilities": init.get("agentCapabilities", {}),
                "authMethods": [
                    {
                        "id": m["id"],
                        "name": str(m.get("name") or m["id"]),
                        "type": str(m.get("type", "agent")),
                    }
                    for m in methods
                ],
                "status": status,
            }
        finally:
            if not retained:
                await client.close()

    async def create(
        self, chat_id: str, agent_id: str, cwd: str, permission_mode: str = ""
    ) -> ManagedSession:
        async with self._lock:
            await self._close_unlocked(chat_id)
            managed = await self._connect(chat_id, agent_id, cwd, None, permission_mode)
            self._sessions[chat_id] = managed
            return managed

    async def resume(
        self,
        chat_id: str,
        agent_id: str,
        session_id: str,
        cwd: str,
        permission_mode: str = "",
    ) -> ManagedSession:
        current = self._sessions.get(chat_id)
        if (
            current
            and current.agent_id == agent_id
            and current.session_id == session_id
            and current.client.is_running
        ):
            current.permission_mode = permission_mode
            current.resumed = True
            return current
        async with self._lock:
            await self._close_unlocked(chat_id)
            managed = await self._connect(
                chat_id, agent_id, cwd, session_id, permission_mode
            )
            self._sessions[chat_id] = managed
            return managed

    async def ensure(self, chat_id: str, config: dict[str, Any]) -> ManagedSession:
        agent_id = str(config.get("acp_agent_id") or "").strip()
        if not agent_id:
            raise ValueError("ACP chat config requires acp_agent_id")
        cwd = str(
            config.get("acp_cwd") or config.get("cwd") or default_acp_cwd(chat_id)
        )
        session_id = str(config.get("acp_session_id") or "").strip()
        permission_mode = str(config.get("permission_mode") or "")
        if session_id:
            return await self.resume(
                chat_id, agent_id, session_id, cwd, permission_mode
            )
        return await self.create(chat_id, agent_id, cwd, permission_mode)

    async def cancel(self, chat_id: str) -> bool:
        current = self._sessions.get(chat_id)
        if current is None:
            return False
        # Release anything waiting on a human so the agent isn't left blocked.
        get_permission_broker().cancel_chat(chat_id)
        await current.client.cancel(current.session_id)
        return True

    async def close(self, chat_id: str) -> None:
        async with self._lock:
            await self._close_unlocked(chat_id)

    async def shutdown(self) -> None:
        await self.logins.shutdown()
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        broker = get_permission_broker()
        for item in sessions:
            broker.cancel_chat(item.chat_id)
        await asyncio.gather(
            *(item.client.close() for item in sessions), return_exceptions=True
        )
        authenticated = list(self._authenticated.values())
        self._authenticated.clear()
        await asyncio.gather(*(client.close() for client, _ in authenticated))

    async def stop(self, chat_id: str) -> None:
        async with self._lock:
            await self._close_unlocked(chat_id)

    async def _connect(
        self,
        chat_id: str,
        agent_id: str,
        cwd: str,
        session_id: str | None,
        permission_mode: str = "",
    ) -> ManagedSession:
        agent = self.registry.get(agent_id)
        if not agent.available:
            raise RuntimeError(
                f"{agent.name} is not available: {agent.display_command} was not found"
            )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=4096)

        async def on_notification(method: str, params: dict[str, Any]) -> None:
            if method == "session/update":
                try:
                    queue.put_nowait(params)
                except asyncio.QueueFull:
                    get_permission_broker().cancel_chat(chat_id)
                    raise ACPError(
                        "ACP update buffer overflow; reconnect and retry"
                    ) from None

        async def on_permission(params: dict[str, Any]) -> dict[str, Any]:
            # Surface the request on the chat stream, then park until decided.
            async def relay(event: dict[str, Any]) -> None:
                queue.put_nowait({PERMISSION_QUEUE_KEY: event})

            # Read the mode off the live session so a resume that changes it wins.
            live = self._sessions.get(chat_id)
            return await get_permission_broker().request(
                chat_id,
                params,
                permission_mode=live.permission_mode if live else permission_mode,
                on_relay=relay,
            )

        # A login may be connection-scoped; keep its process for the next session.
        authenticated = self._authenticated.pop(agent_id, None)
        if authenticated and not authenticated[0].is_running:
            await authenticated[0].close()
            authenticated = None
        if authenticated:
            client, init = authenticated
            client.notification_handler = on_notification
            client.permission_handler = on_permission
        else:
            client = ACPClient(
                agent.command,
                cwd=agent.cwd or cwd,
                env=agent.env,
                notification_handler=on_notification,
                permission_handler=on_permission,
            )
        try:
            if authenticated is None:
                await client.start()
                init = await client.initialize()
            capabilities = (
                init.get("agentCapabilities")
                if isinstance(init.get("agentCapabilities"), dict)
                else {}
            )
            agent_info = (
                init.get("agentInfo") if isinstance(init.get("agentInfo"), dict) else {}
            )
            resumed = False
            restored = False
            resolved_id = ""
            load_error = ""
            if session_id and capabilities.get("loadSession"):
                try:
                    result = await client.load_session(session_id, cwd)
                    resolved_id = str(result.get("sessionId") or session_id)
                    resumed = True
                    restored = True
                except ACPError as exc:
                    if exc.auth_required:
                        raise
                    # The agent advertises loadSession but no longer holds this
                    # id -- codex reports "no rollout found for thread id" once
                    # its rollout file is gone. Losing the history is bad; a
                    # chat that can never send another message is worse, so
                    # fall back to a fresh session and let the caller say so.
                    load_error = str(exc)
                    logger.info(
                        "ACP agent %s could not load session %s (%s); "
                        "starting a fresh session",
                        agent_id,
                        session_id,
                        load_error,
                    )
            elif session_id:
                logger.info(
                    "ACP agent %s does not support session/load; "
                    "starting a fresh session instead of resuming %s",
                    agent_id,
                    session_id,
                )
            if not resolved_id:
                result = await client.new_session(cwd)
                resolved_id = str(result.get("sessionId") or "")
                if not resolved_id:
                    raise RuntimeError("ACP agent did not return a sessionId")
        except (Exception, asyncio.CancelledError):
            await client.close()
            raise
        return ManagedSession(
            chat_id,
            agent_id,
            resolved_id,
            cwd,
            client,
            queue,
            capabilities=capabilities,
            agent_info=agent_info,
            protocol_version=init.get("protocolVersion"),
            resumed=resumed,
            restored=restored,
            permission_mode=permission_mode,
            load_error=load_error,
        )

    async def _close_unlocked(self, chat_id: str) -> None:
        current = self._sessions.pop(chat_id, None)
        if current:
            get_permission_broker().cancel_chat(chat_id)
            await current.client.close()


_manager: ACPManager | None = None


def get_acp_manager() -> ACPManager:
    global _manager
    if _manager is None:
        _manager = ACPManager()
    return _manager
