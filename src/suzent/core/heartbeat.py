"""
Heartbeat Runner: Periodic agent check-ins in persistent sessions.

Unlike cron (isolated, stateless, precise timing), heartbeat checks run in
the context of a specific chat session at a fixed interval.
"""

import asyncio
import time
from datetime import datetime, timezone
import dateutil.parser
from pathlib import Path
from typing import Callable, Dict, Optional

from suzent.config import CONFIG
from suzent.core.base_brain import BaseBrain, get_active
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.core.stream_registry import stream_controls
from suzent.core.chat_processor import ChatProcessor

logger = get_logger(__name__)

HEARTBEAT_OK = "HEARTBEAT_OK"


def get_active_heartbeat() -> Optional["HeartbeatRunner"]:
    """Return the active HeartbeatRunner instance, or None."""
    return get_active(HeartbeatRunner)


class HeartbeatRunner(BaseBrain):
    """
    Runs periodic agent turns in persistent chats that have heartbeat enabled.
    Reads the per-session heartbeat_instructions as a checklist. Suppresses HEARTBEAT_OK responses.
    """

    _brain_name = "HeartbeatRunner"

    def __init__(self, interval_minutes: int = 1):
        # The internal polling resolution is 1 minute
        super().__init__()
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
        """Start the heartbeat loop."""
        from suzent.core.base_brain import _registry

        _registry[type(self)] = self

        self._enabled = True
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"HeartbeatRunner started (polling interval {self.polling_interval_minutes}m)"
        )

    async def enable(self):
        """Enable heartbeat loop."""
        if self._running:
            return
        self._enabled = True
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("HeartbeatRunner enabled.")

    async def disable(self):
        """Disable heartbeat loop."""
        self._enabled = False
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HeartbeatRunner disabled.")

    async def _run_loop(self):
        """Main loop — fires heartbeat checks."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                self._last_error = str(e)

            try:
                await asyncio.sleep(self.polling_interval_minutes * 60)
            except asyncio.CancelledError:
                break

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

            # Read physical file
            hb_path = (
                Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
            )
            instructions = ""
            if hb_path.exists():
                try:
                    instructions = hb_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.error(f"Error reading heartbeat.md for chat {chat_id}: {e}")

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
                }
            )

        return {
            "enabled": self._enabled,
            "running": self._running,
            "polling_interval": self.polling_interval_minutes,
            "active_sessions": sessions,
        }

    async def _tick(self):
        """Check all active heartbeat chats and run if due."""
        db = get_database()
        active_chats = db.get_active_heartbeats()

        now = datetime.now(timezone.utc)
        self._last_run_at = now

        for chat in active_chats:
            cfg = chat.config or {}
            last_run_iso = cfg.get("heartbeat_last_run_at")
            interval = cfg.get("heartbeat_interval_minutes", 30)

            if last_run_iso:
                try:
                    last_run = dateutil.parser.isoparse(last_run_iso)
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                    elapsed = (now - last_run).total_seconds() / 60.0
                    if elapsed < interval:
                        continue
                except Exception as e:
                    logger.error(f"Error parsing last_run_at for chat {chat.id}: {e}")

            # Already pending or actively streaming — skip
            if chat.id in self._pending_heartbeats or chat.id in stream_controls:
                continue

            # Run if due
            hb_path = (
                Path(CONFIG.sandbox_data_path) / "sessions" / chat.id / "heartbeat.md"
            )
            instructions = ""
            if hb_path.exists():
                try:
                    instructions = hb_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.error(f"Error reading heartbeat.md for chat {chat.id}: {e}")

            # Mark as pending so the frontend can pick it up via polling.
            # A fallback task will run it directly after 20 s if no SSE stream appears.
            marked_ts = time.time()
            self._pending_heartbeats[chat.id] = marked_ts
            asyncio.create_task(
                self._deferred_run_task(chat.id, instructions, db, marked_ts)
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
        """Trigger an immediate heartbeat tick for a specific chat."""
        db = get_database()
        chat = db.get_chat(chat_id)
        if chat:
            hb_path = (
                Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
            )
            instructions = ""
            if hb_path.exists():
                try:
                    instructions = hb_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            asyncio.create_task(self._run_chat_heartbeat(chat_id, instructions, db))

    async def _run_chat_heartbeat(self, chat_id: str, instructions: str, db):
        from suzent.prompts import HEARTBEAT_BASE_INSTRUCTIONS

        if instructions.strip():
            instructions = HEARTBEAT_BASE_INSTRUCTIONS + "\n\n" + instructions.strip()
        else:
            instructions = HEARTBEAT_BASE_INSTRUCTIONS

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
            # Note down the latest message count to know how many to rollback if it's HEARTBEAT_OK
            chat = db.get_chat(chat_id)
            initial_message_count = len(chat.messages) if chat else 0

            response_text = await self._run_chat_turn(chat_id, instructions)
            self._last_error = None

            if self._is_heartbeat_ok(response_text):
                logger.debug(f"Heartbeat OK ({chat_id}) -- nothing needs attention")
                self._last_result = HEARTBEAT_OK

                # Rollback messages (prompt + response + tool outputs if any)
                self._rollback_heartbeat_messages(chat_id, initial_message_count, db)
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

            if self._notification_callback and response_text:
                self._notification_callback(f"Chat {chat_id[:8]}: {response_text}")

        except Exception as e:
            logger.error(f"Heartbeat execution failed for {chat_id}: {e}")
            self._last_error = str(e)

    async def _run_chat_turn(self, chat_id: str, instructions: str) -> str:
        from suzent.prompts import HEARTBEAT_PROMPT_TEMPLATE

        prompt = HEARTBEAT_PROMPT_TEMPLATE.format(instructions=instructions)

        processor = ChatProcessor()

        # Read global heartbeat_allowed_tools to determine approval policy.
        heartbeat_allowed_tools: list = []
        try:
            from suzent.routes.heartbeat_routes import _load_heartbeat_config

            heartbeat_allowed_tools = (
                _load_heartbeat_config().get("allowed_tools") or []
            )
        except Exception:
            pass

        config_override = self._build_config_override(heartbeat_allowed_tools)

        try:
            return await processor.process_turn_text(
                chat_id=chat_id,
                user_id=CONFIG.user_id,
                message_content=prompt,
                config_override=config_override,
                is_heartbeat=True,
            )
        except RuntimeError as e:
            self._last_error = str(e)
            return ""

    def _rollback_heartbeat_messages(self, chat_id: str, original_count: int, db):
        """Remove the heartbeat prompt and Ok response if no action was needed."""
        try:
            from sqlmodel import Session
            from sqlalchemy.orm.attributes import flag_modified
            from suzent.database import ChatModel

            with Session(db.engine) as session:
                chat = session.get(ChatModel, chat_id)
                if chat and len(chat.messages) > original_count:
                    extra = len(chat.messages) - original_count
                    chat.messages = chat.messages[:original_count]
                    chat.turn_count = max(0, (chat.turn_count or 0) - 1)
                    flag_modified(chat, "messages")
                    session.commit()
                    logger.debug(
                        f"Rolled back {extra} heartbeat messages from chat {chat_id}"
                    )
        except Exception as e:
            logger.error(f"Failed to rollback heartbeat messages for {chat_id}: {e}")

    def _build_config_override(self, heartbeat_allowed_tools: list = None) -> dict:
        from suzent.agent_manager import build_agent_config

        base: dict = {"memory_enabled": True}
        if heartbeat_allowed_tools:
            # Only auto-approve the explicitly allowed tools.
            base["tool_approval_policy"] = {
                tool: "always_allow" for tool in heartbeat_allowed_tools
            }
        else:
            # Default: auto-approve all tools (original behaviour).
            base["auto_approve_tools"] = True

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
