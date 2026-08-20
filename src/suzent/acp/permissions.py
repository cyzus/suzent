"""Relay ACP ``session/request_permission`` requests to a policy, agent, or human.

ACP agents ask the client to approve tool calls over a reverse JSON-RPC request
and block until they get an answer. Suzent resolves those in three stages:

1. **Policy** — chat ``permission_mode`` of ``auto``/``full_access`` auto-selects
   an allow option without bothering anyone.
2. **Relay** — otherwise the request is surfaced on the chat's event stream as
   ``acp.permission_request`` and parked here until something decides.
3. **Fail closed** — if nothing decides before the deadline, the request is
   cancelled, which is what the agent sees as a denial.

A decision arrives either from a human (``POST /acp/permissions/{id}``) or from
a Suzent agent acting on the same endpoint on the user's behalf.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

# Marker key used to tunnel a permission request through the session update
# queue, so the streaming layer can tell it apart from agent notifications.
PERMISSION_QUEUE_KEY = "_suzent_permission"

# How long a relayed request waits for a decision before failing closed.
DEFAULT_TIMEOUT_SECONDS = 600.0

# ACP option kinds, most-preferred first, for each auto-decision.
_ALLOW_KINDS = ("allow_once", "allow_always")
_REJECT_KINDS = ("reject_once", "reject_always")

# Chat permission modes that never prompt.
_AUTO_MODES = frozenset({"auto", "full_access"})


def select_option(options: list[dict[str, Any]], kinds: tuple[str, ...]) -> str | None:
    """Return the first option id whose ``kind`` matches ``kinds``, in order."""
    for kind in kinds:
        for option in options:
            if isinstance(option, dict) and option.get("kind") == kind:
                option_id = option.get("optionId") or option.get("id")
                if option_id:
                    return str(option_id)
    return None


def _cancelled() -> dict[str, Any]:
    return {"outcome": {"outcome": "cancelled"}}


def _selected(option_id: str) -> dict[str, Any]:
    return {"outcome": {"outcome": "selected", "optionId": option_id}}


@dataclass
class PendingPermission:
    """One in-flight permission request awaiting a decision."""

    request_id: str
    chat_id: str
    session_id: str
    tool_call: dict[str, Any]
    options: list[dict[str, Any]]
    future: asyncio.Future = field(repr=False)
    created_at: float = field(default_factory=time.time)

    def to_event(self) -> dict[str, Any]:
        """Payload streamed to the UI (and readable by an agent)."""
        return {
            "requestId": self.request_id,
            "chatId": self.chat_id,
            "sessionId": self.session_id,
            "toolCall": self.tool_call,
            "options": self.options,
            "createdAt": self.created_at,
        }


class ACPPermissionBroker:
    """Tracks permission requests that are parked awaiting a decision."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingPermission] = {}

    def list_pending(self, chat_id: str | None = None) -> list[dict[str, Any]]:
        return [
            item.to_event()
            for item in self._pending.values()
            if chat_id is None or item.chat_id == chat_id
        ]

    def get(self, request_id: str) -> PendingPermission | None:
        return self._pending.get(request_id)

    def resolve(
        self, request_id: str, *, approved: bool, option_id: str | None = None
    ) -> bool:
        """Settle a parked request. Returns False if it is unknown or already done."""
        pending = self._pending.pop(request_id, None)
        if pending is None or pending.future.done():
            return False
        if not approved:
            pending.future.set_result(_cancelled())
            return True
        chosen = option_id or select_option(pending.options, _ALLOW_KINDS)
        if not chosen:
            # Nothing to select means we cannot express approval; deny instead of
            # sending an outcome the agent will reject.
            logger.warning(
                "ACP permission %s approved but no allow option was offered", request_id
            )
            pending.future.set_result(_cancelled())
            return True
        pending.future.set_result(_selected(chosen))
        return True

    def cancel_chat(self, chat_id: str) -> int:
        """Fail-close every request parked for a chat (stream stopped, chat closed)."""
        stale = [k for k, v in self._pending.items() if v.chat_id == chat_id]
        for request_id in stale:
            pending = self._pending.pop(request_id, None)
            if pending and not pending.future.done():
                pending.future.set_result(_cancelled())
        return len(stale)

    async def request(
        self,
        chat_id: str,
        params: dict[str, Any],
        *,
        permission_mode: str = "",
        on_relay: Any = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Resolve one ``session/request_permission``, prompting only if needed.

        ``on_relay`` is an optional callable invoked with the event payload so the
        caller can push it onto the chat's stream before we start waiting.
        """
        options = [o for o in (params.get("options") or []) if isinstance(o, dict)]
        tool_call = (
            params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
        )

        if str(permission_mode or "").lower() in _AUTO_MODES:
            chosen = select_option(options, _ALLOW_KINDS)
            if chosen:
                return _selected(chosen)
            return _cancelled()

        if not options:
            # No way to express a decision; don't park a request nobody can answer.
            return _cancelled()

        loop = asyncio.get_running_loop()
        request_id = uuid.uuid4().hex
        pending = PendingPermission(
            request_id=request_id,
            chat_id=chat_id,
            session_id=str(params.get("sessionId") or ""),
            tool_call=tool_call,
            options=options,
            future=loop.create_future(),
        )
        self._pending[request_id] = pending

        if on_relay is not None:
            try:
                result = on_relay(pending.to_event())
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "Failed to relay ACP permission request %s", request_id
                )
                self._pending.pop(request_id, None)
                return _cancelled()

        try:
            return await asyncio.wait_for(
                asyncio.shield(pending.future), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.info(
                "ACP permission %s timed out after %ss; denying", request_id, timeout
            )
            return _cancelled()
        except asyncio.CancelledError:
            return _cancelled()
        finally:
            self._pending.pop(request_id, None)


_broker: ACPPermissionBroker | None = None


def get_permission_broker() -> ACPPermissionBroker:
    global _broker
    if _broker is None:
        _broker = ACPPermissionBroker()
    return _broker
