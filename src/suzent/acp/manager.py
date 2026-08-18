"""Lifecycle manager for ACP subprocesses and resumable sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import ACPClient
from .registry import ACPAgentRegistry


@dataclass
class ManagedSession:
    chat_id: str
    agent_id: str
    session_id: str
    cwd: str
    client: ACPClient
    updates: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)


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

    async def create(self, chat_id: str, agent_id: str, cwd: str) -> ManagedSession:
        async with self._lock:
            await self._close_unlocked(chat_id)
            managed = await self._connect(chat_id, agent_id, cwd, None)
            self._sessions[chat_id] = managed
            return managed

    async def resume(
        self, chat_id: str, agent_id: str, session_id: str, cwd: str
    ) -> ManagedSession:
        current = self._sessions.get(chat_id)
        if (
            current
            and current.agent_id == agent_id
            and current.session_id == session_id
        ):
            return current
        async with self._lock:
            await self._close_unlocked(chat_id)
            managed = await self._connect(chat_id, agent_id, cwd, session_id)
            self._sessions[chat_id] = managed
            return managed

    async def ensure(self, chat_id: str, config: dict[str, Any]) -> ManagedSession:
        agent_id = str(config.get("acp_agent_id") or "").strip()
        if not agent_id:
            raise ValueError("ACP chat config requires acp_agent_id")
        cwd = str(config.get("acp_cwd") or config.get("cwd") or Path.cwd())
        session_id = str(config.get("acp_session_id") or "").strip()
        if session_id:
            return await self.resume(chat_id, agent_id, session_id, cwd)
        return await self.create(chat_id, agent_id, cwd)

    async def cancel(self, chat_id: str) -> bool:
        current = self._sessions.get(chat_id)
        if current is None:
            return False
        await current.client.cancel(current.session_id)
        return True

    async def close(self, chat_id: str) -> None:
        async with self._lock:
            await self._close_unlocked(chat_id)

    async def shutdown(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        await asyncio.gather(
            *(item.client.close() for item in sessions), return_exceptions=True
        )

    async def stop(self, chat_id: str) -> None:
        async with self._lock:
            await self._close_unlocked(chat_id)

    async def _connect(
        self, chat_id: str, agent_id: str, cwd: str, session_id: str | None
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

        client = ACPClient(
            agent.command,
            cwd=agent.cwd,
            env=agent.env,
            notification_handler=on_notification,
        )
        await client.start()
        try:
            if session_id:
                result = await client.load_session(session_id, cwd)
                resolved_id = str(result.get("sessionId") or session_id)
            else:
                result = await client.new_session(cwd)
                resolved_id = str(result.get("sessionId") or "")
                if not resolved_id:
                    raise RuntimeError("ACP agent did not return a sessionId")
        except Exception:
            await client.close()
            raise
        return ManagedSession(chat_id, agent_id, resolved_id, cwd, client, queue)

    async def _close_unlocked(self, chat_id: str) -> None:
        current = self._sessions.pop(chat_id, None)
        if current:
            await current.client.close()


_manager: ACPManager | None = None


def get_acp_manager() -> ACPManager:
    global _manager
    if _manager is None:
        _manager = ACPManager()
    return _manager
