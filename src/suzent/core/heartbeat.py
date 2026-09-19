"""
Heartbeat Runner: agent check-ins that run inside a live conversation.

Timing lives in :mod:`suzent.core.scheduler` -- a heartbeat is a scheduled task
row like any other. What stays here is *execution*: how to take a background
turn in a chat someone may be using, tell an answer worth showing from a
routine all-clear, and roll a quiet check back out of the transcript.

That executor is generic (:meth:`HeartbeatRunner.run_bound_turn`), so any
chat-bound scheduled task reuses it. Heartbeats themselves keep one extra step:
they are announced as *pending* first, giving an attached frontend the chance
to claim and stream the turn before the server runs it headlessly.
"""

import asyncio
import time
from datetime import datetime, timezone
import dateutil.parser
from typing import Callable, Dict, Optional

from suzent.config import CONFIG
from suzent.core.base_brain import BaseBrain, get_active
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.core.stream_registry import stream_controls

logger = get_logger(__name__)

HEARTBEAT_OK = "HEARTBEAT_OK"


def get_active_heartbeat() -> Optional["HeartbeatRunner"]:
    """Return the active HeartbeatRunner instance, or None."""
    return get_active(HeartbeatRunner)


class HeartbeatRunner(BaseBrain):
    """
    Executes agent turns inside persistent chats, for heartbeats and for any
    other chat-bound scheduled task. Reads the per-session heartbeat.md as a
    checklist. Suppresses HEARTBEAT_OK responses.
    """

    _brain_name = "HeartbeatRunner"

    def __init__(self, interval_minutes: int = 1):
        super().__init__()
        # Kept for status reporting only: the scheduler's tick is the real
        # resolution now that it owns heartbeat timing.
        self.polling_interval_minutes = interval_minutes
        self._enabled = False
        self._last_run_at: Optional[datetime] = None
        self._last_result: Optional[str] = None
        self._last_error: Optional[str] = None
        self._notification_callback: Optional[Callable[[str], None]] = None
        # Tracks chats whose heartbeat is due, pending frontend pickup.
        # Maps chat_id → timestamp when it was marked pending.
        self._pending_heartbeats: Dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_notification_callback(self, callback: Callable[[str], None]):
        """Set callback for delivering heartbeat alerts."""
        self._notification_callback = callback

    async def start(self):
        """Register as the active runner. The scheduler drives the clock."""
        from suzent.core.base_brain import _registry

        _registry[type(self)] = self

        self._enabled = True
        self._running = True
        logger.info("HeartbeatRunner started (scheduler-driven).")

    async def enable(self):
        """Allow due heartbeats to run."""
        self._enabled = True
        self._running = True
        logger.info("HeartbeatRunner enabled.")

    async def disable(self):
        """Stop running heartbeats; scheduled rows stay armed but are skipped."""
        self._enabled = False
        self._running = False
        self._pending_heartbeats.clear()
        logger.info("HeartbeatRunner disabled.")

    def get_status(self, chat_id: Optional[str] = None) -> dict:
        """Return system status or specific chat status if requested."""
        if chat_id:
            db = get_database()
            chat = db.get_chat(chat_id)
            if not chat:
                return {
                    "enabled": False,
                    "running": self._running,
                    "interval_minutes": 30,
                    "heartbeat_instructions": "",
                }
            cfg = chat.config or {}

            instructions = self.read_instructions(chat_id)

            return {
                "enabled": cfg.get("heartbeat_enabled", False),
                "running": self._running,
                "interval_minutes": cfg.get("heartbeat_interval_minutes", 30),
                "heartbeat_instructions": instructions,
                "last_run_at": cfg.get("heartbeat_last_run_at"),
                "last_result": cfg.get("heartbeat_last_result") or self._last_result,
                "last_error": self._last_error,
                "heartbeat_due": chat_id in self._pending_heartbeats,
            }

        db = get_database()
        active_chats = db.get_active_heartbeats()
        sessions = []
        for chat in active_chats:
            cfg = chat.config or {}
            sessions.append(
                {
                    "chat_id": chat.id,
                    "title": chat.title,
                    "interval_minutes": cfg.get("heartbeat_interval_minutes", 30),
                    "last_run_at": cfg.get("heartbeat_last_run_at"),
                    "is_running": chat.id in stream_controls,
                    "unread_count": cfg.get("unread_count", 0),
                }
            )

        return {
            "enabled": self._enabled,
            "running": self._running,
            "polling_interval": self.polling_interval_minutes,
            "active_sessions": sessions,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_error": self._last_error,
        }

    def read_instructions(self, chat_id: str) -> str:
        """Read a chat's heartbeat.md checklist, or '' when it has none."""
        hb_path = get_database().get_project_dir(chat_id) / "heartbeat.md"
        if not hb_path.exists():
            return ""
        try:
            return hb_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Error reading heartbeat.md for chat {chat_id}: {e}")
            return ""

    def mark_heartbeat_pending(self, chat_id: str) -> None:
        """Announce a due heartbeat, letting an attached frontend claim it.

        Called by the scheduler when a heartbeat row comes due. The chat is
        marked pending so a watching frontend can pick it up and stream the
        turn where the user can see it; a fallback task runs it headlessly if
        nobody claims it within 20 seconds.
        """
        if not self._enabled:
            return
        if chat_id in self._pending_heartbeats or chat_id in stream_controls:
            return

        instructions = self.read_instructions(chat_id)
        marked_ts = time.time()
        self._pending_heartbeats[chat_id] = marked_ts
        asyncio.create_task(
            self._deferred_run_task(chat_id, instructions, get_database(), marked_ts)
        )

    async def _deferred_run_task(
        self, chat_id: str, instructions: str, db, marked_ts: float
    ):
        """Wait 20 s for the frontend to pick up the heartbeat; run directly if it doesn't."""
        await asyncio.sleep(20)

        # If the pending entry was cleared (frontend claimed it or a newer tick came), skip.
        if self._pending_heartbeats.get(chat_id) != marked_ts:
            return

        self._pending_heartbeats.pop(chat_id, None)

        # If the frontend already started a stream, the heartbeat is in progress.
        if chat_id in stream_controls:
            return

        # Check whether the frontend updated heartbeat_last_run_at since we marked pending.
        try:
            chat = db.get_chat(chat_id)
            cfg = (chat.config or {}) if chat else {}
            last_run_iso = cfg.get("heartbeat_last_run_at")
            if last_run_iso:
                last_run_ts = dateutil.parser.isoparse(last_run_iso).timestamp()
                if last_run_ts >= marked_ts - 5:
                    # Frontend already ran the heartbeat
                    return
        except Exception:
            pass

        # Fall back to direct execution (app is backgrounded / frontend not watching).
        asyncio.create_task(self._run_chat_heartbeat(chat_id, instructions, db))

    async def trigger_now(self, chat_id: str):
        """Run a heartbeat for a chat right now, bypassing its schedule."""
        db = get_database()
        if db.get_chat(chat_id):
            asyncio.create_task(
                self._run_chat_heartbeat(chat_id, self.read_instructions(chat_id), db)
            )

    async def _run_chat_heartbeat(self, chat_id: str, instructions: str, db):
        """Run a heartbeat check and publish anything it found."""
        if chat_id in stream_controls:
            logger.debug(f"Heartbeat skipped for {chat_id}: stream already active")
            return

        # Update last_run_at early to avoid duplicate rapid ticks (single-session write)
        try:
            from sqlmodel import Session
            from sqlalchemy.orm.attributes import flag_modified
            from suzent.database import ChatModel

            with Session(db.engine) as session:
                chat = session.get(ChatModel, chat_id)
                if chat:
                    chat.config["heartbeat_last_run_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    chat.config.pop("heartbeat_last_result", None)  # clear stale result
                    chat.updated_at = datetime.now()
                    flag_modified(chat, "config")
                    session.commit()
        except Exception as e:
            logger.error(f"Failed to update heartbeat_last_run_at: {e}")

        try:
            response_text = await self.run_bound_turn(
                chat_id,
                self.build_heartbeat_reminder(instructions),
                suppress_ok=True,
                heartbeat_approvals=True,
            )
            self._last_error = None

            if not response_text:
                logger.debug(f"Heartbeat OK ({chat_id}) -- nothing needs attention")
                self._last_result = HEARTBEAT_OK
                return

            self._last_result = response_text
            logger.info(f"Heartbeat alert ({chat_id}): {response_text[:100]}")

            # Persist result per-session so the frontend poll can detect it
            try:
                from sqlmodel import Session as _Session
                from sqlalchemy.orm.attributes import flag_modified as _fm
                from suzent.database import ChatModel as _CM

                with _Session(db.engine) as _s:
                    _chat = _s.get(_CM, chat_id)
                    if _chat:
                        _chat.config["heartbeat_last_result"] = response_text
                        _chat.updated_at = datetime.now()
                        _fm(_chat, "config")
                        _s.commit()
            except Exception as _e:
                logger.warning(f"Failed to persist heartbeat_last_result: {_e}")

            db.set_last_result_at(chat_id)

            if self._notification_callback and response_text:
                self._notification_callback(f"Chat {chat_id[:8]}: {response_text}")

        except Exception as e:
            logger.error(f"Heartbeat execution failed for {chat_id}: {e}")
            self._last_error = str(e)

    @staticmethod
    def build_heartbeat_reminder(instructions: str) -> str:
        """The check-in prompt: shared base rules plus this chat's checklist."""
        from suzent.prompts import (
            HEARTBEAT_BASE_INSTRUCTIONS,
            HEARTBEAT_PROMPT_TEMPLATE,
        )

        extra_inst = f"\n\n{instructions.strip()}" if instructions.strip() else ""
        return HEARTBEAT_PROMPT_TEMPLATE.format(
            base_instructions=HEARTBEAT_BASE_INSTRUCTIONS, extra_instructions=extra_inst
        )

    async def run_bound_turn(
        self,
        chat_id: str,
        reminder: str,
        *,
        suppress_ok: bool = False,
        model_override: Optional[str] = None,
        heartbeat_approvals: bool = False,
        persist_to_chat: bool = False,
        answer_label: Optional[str] = None,
    ) -> str:
        """Run one background turn inside an existing chat.

        This is the executor behind every chat-bound scheduled task, heartbeats
        included. Returns the agent's answer, or "" when ``suppress_ok`` is set
        and the turn reported nothing worth surfacing -- in that case its
        messages are rolled back, so a quiet check leaves the conversation
        exactly as it found it.

        ``answer_label`` names the task an answer belongs to. A suppressible
        turn is never rebuilt into the transcript, so when nobody was streaming
        it there is nothing in the chat to show for it -- pass a label and an
        answer that is not a no-op gets written in under it. Heartbeats leave
        it unset: they have their own result channel in the chat's config.

        ``persist_to_chat`` decides whether the turn joins the conversation's
        visible transcript. A suppressible check must not: rollback owns its
        message state, and a persisted internal prompt would survive every
        failure path. A task that speaks for itself must, or its answer would
        be recorded as a successful run that nobody can see -- which is the
        whole point of binding it to a chat.

        ``heartbeat_approvals`` opts into the global heartbeat allow-list. It
        is off by default and only heartbeats pass it: those tools were
        approved for a check-in the user configured, and handing the same
        blanket approval to an arbitrary scheduled prompt -- including one the
        agent wrote for itself -- would widen it well past what was agreed to.

        Raises whatever the turn raises: the scheduler needs a failed run to
        look like a failure so it can retry.
        """
        if chat_id in stream_controls:
            logger.debug(f"Bound turn skipped for {chat_id}: stream already active")
            return ""

        db = get_database()
        chat = db.get_chat(chat_id)
        # Note the message count so a suppressed turn can be rolled back to it.
        initial_message_count = len(chat.messages) if chat else 0

        response_text = await self._run_chat_turn(
            chat_id,
            reminder,
            model_override=model_override,
            heartbeat_approvals=heartbeat_approvals,
            persist_to_chat=persist_to_chat,
        )

        if suppress_ok:
            if self._is_heartbeat_ok(response_text):
                self._rollback_heartbeat_messages(chat_id, initial_message_count, db)
                return ""
            if answer_label:
                self._record_bound_answer(
                    chat_id, response_text, initial_message_count, db, answer_label
                )

        return response_text

    def _record_bound_answer(
        self, chat_id: str, text: str, original_count: int, db, label: str
    ) -> None:
        """Write a suppressible turn's answer into the chat it was bound to.

        Ordering is the point: the answer is classified first and written
        second, so there is never a moment where the transcript holds a turn
        that a rollback still has to take back out. That window is what makes
        persist-then-roll-back fragile -- a failure in between strands the row.

        A turn someone was streaming already left a draft row behind, which is
        why this checks the message count instead of appending unconditionally.
        """
        try:
            chat = db.get_chat(chat_id)
            if chat and len(chat.messages) > original_count:
                return
            # A bare answer with no lead-in reads as the agent talking to
            # itself; the header says which task woke it, and matches the
            # wording cron triggers use so the two coalesce the same way.
            db.append_chat_message(
                chat_id,
                {"role": "system_triggered", "content": f"**Scheduled Task: {label}**"},
            )
            db.append_chat_message(chat_id, {"role": "assistant", "content": text})
        except Exception as e:
            logger.error(f"Failed to record scheduled task answer in {chat_id}: {e}")

    async def _run_chat_turn(
        self,
        chat_id: str,
        reminder: str,
        *,
        model_override: Optional[str] = None,
        heartbeat_approvals: bool = False,
        persist_to_chat: bool = False,
    ) -> str:
        from suzent.core.chat_processor import ChatProcessor

        processor = ChatProcessor()

        # Read global heartbeat_allowed_tools to determine approval policy.
        # Only a heartbeat gets them; see run_bound_turn.
        heartbeat_allowed_tools: list = []
        if heartbeat_approvals:
            try:
                from suzent.routes.heartbeat_routes import _load_heartbeat_config

                heartbeat_allowed_tools = (
                    _load_heartbeat_config().get("allowed_tools") or []
                )
            except Exception:
                pass

        config_override = self._build_config_override(
            heartbeat_allowed_tools, model_override=model_override
        )

        return await processor.process_background_turn(
            chat_id=chat_id,
            user_id=CONFIG.user_id,
            message_content="",
            config_override=config_override,
            # is_heartbeat gates message persistence (skip_messages) as well as
            # goal counting and trigger rows, so a turn meant to be seen has to
            # go through the ordinary path.
            is_heartbeat=not persist_to_chat,
            system_reminders=[reminder],
        )

    def _rollback_heartbeat_messages(self, chat_id: str, original_count: int, db):
        """Remove the heartbeat prompt and Ok response if no action was needed."""
        try:
            chat = db.get_chat(chat_id)
            if chat and len(chat.messages) > original_count:
                extra = len(chat.messages) - original_count
                # rewrite_chat_messages refreshes the sidebar summary + FTS index so
                # the rolled-back state doesn't leave a stale message count/preview.
                db.rewrite_chat_messages(
                    chat_id,
                    chat.messages[:original_count],
                    turn_count_delta=-1,
                )
                logger.debug(
                    f"Rolled back {extra} heartbeat messages from chat {chat_id}"
                )
        except Exception as e:
            logger.error(f"Failed to rollback heartbeat messages for {chat_id}: {e}")

    def _build_config_override(
        self,
        heartbeat_allowed_tools: list = None,
        *,
        model_override: Optional[str] = None,
    ) -> dict:
        from suzent.agent_manager import build_agent_config

        base: dict = {
            "memory_enabled": True,
            "permission_mode": "auto",
            "interaction_profile": "headless",
        }
        if model_override:
            base["model"] = model_override
        if heartbeat_allowed_tools:
            # Only auto-approve the explicitly allowed tools.
            base["tool_approval_policy"] = {
                tool: "always_allow" for tool in heartbeat_allowed_tools
            }
        return build_agent_config(base, require_social_tool=False)

    def _is_heartbeat_ok(self, response: str) -> bool:
        if not response or response == HEARTBEAT_OK:
            return True

        if response.startswith(HEARTBEAT_OK):
            remaining = response[len(HEARTBEAT_OK) :].strip()
        elif response.endswith(HEARTBEAT_OK):
            remaining = response[: -len(HEARTBEAT_OK)].strip()
        else:
            return False

        return len(remaining) <= 300
