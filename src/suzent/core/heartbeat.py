"""
Heartbeat Runner: Periodic agent check-ins in a persistent session.

Unlike cron (isolated, stateless, precise timing), heartbeat runs in a
dedicated persistent chat at a fixed interval. The agent reads HEARTBEAT.md,
checks whatever is listed, and either surfaces alerts or replies HEARTBEAT_OK.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from suzent.config import CONFIG
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.streaming import stream_controls

logger = get_logger(__name__)

HEARTBEAT_OK = "HEARTBEAT_OK"
HEARTBEAT_CHAT_ID = "heartbeat-main"
HEARTBEAT_MD_FILENAME = "HEARTBEAT.md"

_active_instance: Optional["HeartbeatRunner"] = None


def get_active_heartbeat() -> Optional["HeartbeatRunner"]:
    """Return the active HeartbeatRunner instance, or None."""
    return _active_instance


class HeartbeatRunner:
    """
    Runs periodic agent turns in a dedicated persistent chat.
    Reads HEARTBEAT.md as a checklist. Suppresses HEARTBEAT_OK responses.
    """

    def __init__(self, interval_minutes: int = 30):
        self.interval_minutes = interval_minutes
        self._enabled = False
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_run_at: Optional[datetime] = None
        self._last_result: Optional[str] = None
        self._last_error: Optional[str] = None
        self._notification_callback: Optional[Callable[[str], None]] = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def heartbeat_md_path(self) -> Path:
        return Path(CONFIG.sandbox_data_path) / "shared" / HEARTBEAT_MD_FILENAME

    def set_notification_callback(self, callback: Callable[[str], None]):
        """Set callback for delivering heartbeat alerts."""
        self._notification_callback = callback

    async def start(self):
        """Start the heartbeat loop if HEARTBEAT.md exists."""
        global _active_instance
        _active_instance = self

        if not self.heartbeat_md_path.exists():
            logger.info(
                f"Heartbeat disabled: {self.heartbeat_md_path} not found. "
                "Create it to enable heartbeat."
            )
            return

        self._enabled = True
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"HeartbeatRunner started (every {self.interval_minutes}m, "
            f"checklist: {self.heartbeat_md_path})"
        )

    async def stop(self):
        """Stop the heartbeat loop."""
        global _active_instance
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _active_instance = None
        logger.info("HeartbeatRunner stopped.")

    async def enable(self):
        """Enable heartbeat and start the loop."""
        if self._running:
            return
        if not self.heartbeat_md_path.exists():
            logger.warning("Cannot enable heartbeat: HEARTBEAT.md not found")
            return
        self._enabled = True
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("HeartbeatRunner enabled.")

    async def disable(self):
        """Disable heartbeat and stop the loop."""
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
        """Main loop — fires heartbeat at fixed intervals."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat tick error: {e}")
                self._last_error = str(e)

            try:
                await asyncio.sleep(self.interval_minutes * 60)
            except asyncio.CancelledError:
                break

    async def trigger_now(self):
        """Trigger an immediate heartbeat tick."""
        asyncio.create_task(self._tick())

    def get_status(self) -> dict:
        """Return current heartbeat status."""
        return {
            "enabled": self._enabled,
            "running": self._running,
            "interval_minutes": self.interval_minutes,
            "heartbeat_md_exists": self.heartbeat_md_path.exists(),
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_result": self._last_result,
            "last_error": self._last_error,
        }

    # -- Internal ------------------------------------------------------------

    async def _tick(self):
        """Single heartbeat tick."""
        if not (checklist := self._read_heartbeat_md()):
            logger.debug("Heartbeat skipped: HEARTBEAT.md is empty or missing")
            return

        if HEARTBEAT_CHAT_ID in stream_controls:
            logger.debug("Heartbeat skipped: stream already active")
            return

        self._ensure_heartbeat_chat()
        self._last_run_at = datetime.now()

        try:
            response_text = await self._run_chat_turn(checklist)
            self._last_error = None

            if self._is_heartbeat_ok(response_text):
                logger.debug("Heartbeat OK -- nothing needs attention")
                self._last_result = HEARTBEAT_OK
                return

            self._last_result = response_text
            logger.info(f"Heartbeat alert: {response_text[:100]}")

            if self._notification_callback and response_text:
                self._notification_callback(response_text)

        except Exception as e:
            logger.error(f"Heartbeat execution failed: {e}")
            self._last_error = str(e)

    async def _run_chat_turn(self, checklist: str) -> str:
        """Run a ChatProcessor turn with the checklist and return the response."""
        from suzent.core.chat_processor import ChatProcessor

        processor = ChatProcessor()
        config_override = self._build_config_override()

        prompt = (
            "Read the following HEARTBEAT.md checklist and follow it strictly. "
            "Do not infer or repeat old tasks from prior messages. "
            f"If nothing needs attention, reply HEARTBEAT_OK.\n\n"
            f"---\n{checklist}\n---"
        )

        full_response = ""
        async for chunk in processor.process_turn(
            chat_id=HEARTBEAT_CHAT_ID,
            user_id=CONFIG.user_id,
            message_content=prompt,
            config_override=config_override,
        ):
            if not chunk.startswith("data: "):
                continue
            try:
                data = json.loads(chunk[6:].strip())
                if data.get("type") == "final_answer":
                    full_response = data.get("data", "")
                elif data.get("type") == "error":
                    self._last_error = str(data.get("data"))
                    return ""
            except json.JSONDecodeError:
                pass

        return full_response.strip()

    def _build_config_override(self) -> dict:
        """Build config override, resolving model from user preferences."""
        config: dict = {"memory_enabled": True}

        try:
            db = get_database()
            if (prefs := db.get_user_preferences()) and prefs.model:
                config["model"] = prefs.model
        except Exception as e:
            logger.warning(f"Failed to load user preferences for heartbeat: {e}")

        return config

    def _read_heartbeat_md(self) -> Optional[str]:
        """Read HEARTBEAT.md, return None if missing or has no meaningful content."""
        path = self.heartbeat_md_path
        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return None

        # Skip if only blank lines and markdown headers
        has_content = any(
            line.strip() and not line.strip().startswith("#")
            for line in content.splitlines()
        )
        return content if has_content else None

    def _is_heartbeat_ok(self, response: str) -> bool:
        """Check if response is a HEARTBEAT_OK acknowledgment."""
        if not response or response == HEARTBEAT_OK:
            return True

        # Contains HEARTBEAT_OK at start or end with minimal extra content
        if response.startswith(HEARTBEAT_OK):
            remaining = response[len(HEARTBEAT_OK) :].strip()
        elif response.endswith(HEARTBEAT_OK):
            remaining = response[: -len(HEARTBEAT_OK)].strip()
        else:
            return False

        return len(remaining) <= 300

    def _ensure_heartbeat_chat(self):
        """Ensure the persistent heartbeat chat exists."""
        db = get_database()
        if not db.get_chat(HEARTBEAT_CHAT_ID):
            db.create_chat(
                title="Heartbeat",
                config={"platform": "heartbeat"},
                chat_id=HEARTBEAT_CHAT_ID,
            )
