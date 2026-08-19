"""Lifecycle manager for ACP subprocesses and resumable sessions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import ACPClient
from .permissions import PERMISSION_QUEUE_KEY, get_permission_broker
from .registry import ACPAgentRegistry

logger = logging.getLogger(__name__)


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
    # False when a resume was requested but the agent could not load the prior
    # session, so a fresh one was started instead.
    resumed: bool = False
    # Chat permission_mode; 'auto'/'full_access' skip the approval prompt.
    permission_mode: str = ""


class ACPManager:
    def __init__(self, registry: ACPAgentRegistry | None = None):
        self.registry = registry or ACPAgentRegistry()
        self._sessions: dict[str, ManagedSession] = {}
        self._lock = asyncio.Lock()

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
        ):
            current.permission_mode = permission_mode
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
        cwd = str(config.get("acp_cwd") or config.get("cwd") or Path.cwd())
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
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        broker = get_permission_broker()
        for item in sessions:
            broker.cancel_chat(item.chat_id)
        await asyncio.gather(
            *(item.client.close() for item in sessions), return_exceptions=True
        )

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
                f"ACP agent executable is not available: {agent.command[0]}"
            )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def on_notification(method: str, params: dict[str, Any]) -> None:
            if method == "session/update":
                await queue.put(params)

        async def on_permission(params: dict[str, Any]) -> dict[str, Any]:
            # Surface the request on the chat stream, then park until decided.
            async def relay(event: dict[str, Any]) -> None:
                await queue.put({PERMISSION_QUEUE_KEY: event})

            # Read the mode off the live session so a resume that changes it wins.
            live = self._sessions.get(chat_id)
            return await get_permission_broker().request(
                chat_id,
                params,
                permission_mode=live.permission_mode if live else permission_mode,
                on_relay=relay,
            )

        client = ACPClient(
            agent.command,
            cwd=agent.cwd,
            env=agent.env,
            notification_handler=on_notification,
            permission_handler=on_permission,
        )
        await client.start()
        try:
            # ACP requires `initialize` before any session method.
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
            if session_id and capabilities.get("loadSession"):
                result = await client.load_session(session_id, cwd)
                resolved_id = str(result.get("sessionId") or session_id)
                resumed = True
            else:
                if session_id:
                    logger.info(
                        "ACP agent %s does not support session/load; "
                        "starting a fresh session instead of resuming %s",
                        agent_id,
                        session_id,
                    )
                result = await client.new_session(cwd)
                resolved_id = str(result.get("sessionId") or "")
                if not resolved_id:
                    raise RuntimeError("ACP agent did not return a sessionId")
        except Exception:
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
            permission_mode=permission_mode,
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
