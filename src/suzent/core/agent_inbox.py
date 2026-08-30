"""Durable dispatcher for messages sent between agent-backed chat sessions."""

import asyncio
import json
import os
import traceback
import uuid
from typing import Any, Optional

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import logger

_POLL_INTERVAL_SECONDS = 1.0
_LEASE_SECONDS = 180
_DELIVERY_MARKER_PREFIX = "suzent-agent-inbox"


# Fallback ceiling for waiting out a busy target when its run cannot take an
# injected message (no live pydantic-ai run, or it ended before draining). The
# injection path above handles the normal case, so reaching this is unusual.
_BUSY_TARGET_WAIT_SECONDS = 120.0


def _delivery_marker(message_id: str) -> str:
    return f"<!-- {_DELIVERY_MARKER_PREFIX}:{message_id} -->"


class AgentInboxDispatcher:
    """Claims durable inbox rows and delivers them as background chat turns."""

    def __init__(self, poll_interval_seconds: float = _POLL_INTERVAL_SECONDS):
        self.poll_interval_seconds = poll_interval_seconds
        self.worker_id = f"{os.getpid()}-{uuid.uuid4().hex[:12]}"
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._wake_event = asyncio.Event()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._run(), name=f"agent_inbox_{self.worker_id}"
        )
        logger.info("Agent inbox dispatcher started")

    async def stop(self) -> None:
        self._running = False
        self._wake_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Agent inbox dispatcher stopped")

    def notify(self) -> None:
        """Wake the local worker after a producer inserts a message."""
        self._wake_event.set()

    async def _run(self) -> None:
        while self._running:
            delivered_any = await self._drain_available()
            if delivered_any:
                continue
            try:
                await asyncio.wait_for(
                    self._wake_event.wait(), timeout=self.poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass
            finally:
                self._wake_event.clear()

    async def _drain_available(self) -> bool:
        delivered_any = False
        while self._running:
            message = get_database().claim_next_agent_message(
                worker_id=self.worker_id, lease_seconds=_LEASE_SECONDS
            )
            if message is None:
                return delivered_any
            delivered_any = True
            await self._deliver_claimed(message)
        return delivered_any

    async def _deliver_claimed(self, message: dict[str, Any]) -> None:
        message_id = str(message["message_id"])
        try:
            if message.get(
                "transport", "local"
            ) == "local" and self._was_already_persisted(message):
                get_database().acknowledge_agent_message(
                    message_id, worker_id=self.worker_id
                )
                return
            await self._deliver(message)
            if not get_database().acknowledge_agent_message(
                message_id, worker_id=self.worker_id
            ):
                logger.warning(
                    "Agent inbox delivery {} completed after its lease changed",
                    message_id,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            retry_cap = 3600 if message.get("transport") == "suzent_peer" else 60
            retry_delay = min(retry_cap, 2 ** int(message.get("attempts", 1)))
            get_database().retry_agent_message(
                message_id,
                worker_id=self.worker_id,
                error=str(exc),
                retry_delay_seconds=retry_delay,
            )
            logger.error(
                "Agent inbox delivery {} failed: {}\n{}",
                message_id,
                exc,
                traceback.format_exc(),
            )

    async def _deliver(self, message: dict[str, Any]) -> None:
        """Dispatch a leased row through its configured transport."""
        transport = str(message.get("transport") or "local")
        if transport == "local":
            await self._run_target_turn(message)
            return
        if transport == "suzent_peer":
            from suzent.nodes.agent_transport import get_peer_agent_transport

            await get_peer_agent_transport().deliver(message)
            return
        raise RuntimeError(f"Unsupported agent message transport '{transport}'")

    async def _inject_into_live_run(
        self, control: Any, chat_id: str, content: str, is_subagent_result: bool
    ) -> bool:
        """Deliver `content` into the target's in-flight turn.

        Unlike a steer, this tears nothing down: the run picks the message up at
        its next model request (or as a redirect if it would otherwise end), so
        the work already done in that turn is kept. Returns True only once the run
        confirms the message reached its history -- an unconfirmed injection falls
        back to running a fresh turn, which is correct but loses no message.
        """
        inject = getattr(control, "inject", None)
        if inject is None:
            return False

        from suzent.core.system_reminder import wrap_in_system_reminder

        payload = (
            wrap_in_system_reminder(content, display_trigger=content)
            if is_subagent_result
            else content
        )
        enqueue_id = inject(payload)
        if not enqueue_id:
            return False

        delivered = control.injection_delivered(enqueue_id)
        # The only way an 'asap' message never lands is the run dying first, so
        # race delivery against the run finishing.
        waiters = [
            asyncio.ensure_future(delivered.wait()),
            asyncio.ensure_future(control.completed_event.wait()),
        ]
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waiters:
                waiter.cancel()
        if delivered.is_set():
            logger.debug("Injected inbox message into live run for chat {}", chat_id)
            return True
        return False

    def _was_already_persisted(self, message: dict[str, Any]) -> bool:
        chat = get_database().get_chat(str(message["target_chat_id"]))
        if chat is None:
            raise RuntimeError(
                f"Target agent '{message['target_chat_id']}' no longer exists"
            )
        marker = _delivery_marker(str(message["message_id"]))
        return marker in json.dumps(chat.messages or [], ensure_ascii=False)

    async def _run_target_turn(self, message: dict[str, Any]) -> None:
        from suzent.agent_manager import build_agent_config
        from suzent.core.chat_processor import ChatProcessor
        from suzent.core.stream_registry import (
            get_background_turn_lock,
            stream_controls,
        )

        target_chat_id = str(message["target_chat_id"])
        target_chat = get_database().get_chat(target_chat_id)
        if target_chat is None:
            raise RuntimeError(f"Target agent '{target_chat_id}' no longer exists")

        sender = None
        sender_chat_id = message.get("sender_chat_id")
        if sender_chat_id:
            sender = get_database().get_chat(str(sender_chat_id))
        payload = message.get("payload") or {}
        sender_label = str(
            payload.get("sender_label")
            or (sender.title if sender is not None else sender_chat_id or "system")
        )
        sender_reference = str(
            payload.get("sender_agent_id") or sender_chat_id or "system"
        )
        marker = _delivery_marker(str(message["message_id"]))
        is_subagent_result = message.get("kind") == "subagent_result"
        if is_subagent_result:
            # Sub-agent completion is an autonomous trigger, like cron and
            # heartbeat, rather than a new utterance from the user. Keep the
            # durable marker inside the reminder so retries remain idempotent.
            delivered_content = f"{message['content']}\n{marker}"
        else:
            delivered_content = (
                f"[Agent message from {sender_label} ({sender_reference})]\n"
                f"{marker}\n{message['content']}"
            )

        base_config = dict(target_chat.config or {})
        runtime = base_config.get("runtime", "native")
        subagent_runtime = base_config.get("subagent_runtime", "native")
        base_config["interaction_profile"] = "headless"
        if message.get("kind") == "remote_agent_message":
            base_config["permission_mode"] = "auto"
        config_override = build_agent_config(base_config, require_social_tool=False)

        async with get_background_turn_lock(target_chat_id):
            control = stream_controls.get(target_chat_id)
            if control is not None and not control.completed_event.is_set():
                # The target is mid-turn. Hand the message to that turn rather than
                # waiting it out: a parent busy for longer than the old 120s cap is
                # working, not stuck, and letting the wait expire burned one of the
                # five delivery attempts before dropping the message for good.
                if await self._inject_into_live_run(
                    control, target_chat_id, delivered_content, is_subagent_result
                ):
                    return
                await asyncio.wait_for(
                    control.completed_event.wait(),
                    timeout=_BUSY_TARGET_WAIT_SECONDS,
                )

            if runtime == "acp" or subagent_runtime == "acp":
                from suzent.acp.runtime import run_acp_turn_text
                from suzent.core.system_reminder import wrap_in_system_reminder

                await run_acp_turn_text(
                    target_chat_id,
                    wrap_in_system_reminder(
                        delivered_content, display_trigger=delivered_content
                    )
                    if is_subagent_result
                    else delivered_content,
                    config_override,
                    None,
                )
            else:
                await ChatProcessor().process_background_turn(
                    chat_id=target_chat_id,
                    user_id=CONFIG.user_id,
                    message_content="" if is_subagent_result else delivered_content,
                    config_override=config_override,
                    system_reminders=[delivered_content]
                    if is_subagent_result
                    else None,
                    incoming_citation_sources=list(
                        payload.get("citation_sources") or []
                    ),
                )


_dispatcher: Optional[AgentInboxDispatcher] = None


def get_agent_inbox_dispatcher() -> AgentInboxDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AgentInboxDispatcher()
    return _dispatcher


def enqueue_agent_message(
    *,
    target_chat_id: str,
    content: str,
    sender_chat_id: Optional[str],
    message_id: Optional[str] = None,
    transport: str = "local",
    destination_peer_id: Optional[str] = None,
    kind: str = "agent_message",
    payload: Optional[dict[str, Any]] = None,
    max_attempts: int = 5,
) -> tuple[dict[str, Any], bool]:
    """Persist one message and wake the local dispatcher when it is running."""
    resolved_id = message_id or f"msg_{uuid.uuid4().hex}"
    record, created = get_database().enqueue_agent_message(
        message_id=resolved_id,
        sender_chat_id=sender_chat_id,
        target_chat_id=target_chat_id,
        content=content,
        transport=transport,
        destination_peer_id=destination_peer_id,
        kind=kind,
        payload=payload,
        max_attempts=max_attempts,
    )
    if created:
        get_agent_inbox_dispatcher().notify()
    return record, created
