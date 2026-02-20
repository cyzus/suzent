"""
Session lifecycle management.

Provides configurable reset policies for sessions:
- Daily reset at a specific hour (e.g., 4 AM)
- Idle timeout after N minutes of inactivity
- Max turn limit per session

Inspired by OpenClaw's session key mapping and reset policies.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from suzent.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SessionPolicy:
    """Configurable session reset policy."""

    daily_reset_hour: int = 4  # Reset at this UTC hour (0-23), 0 = disabled
    idle_timeout_minutes: int = 0  # 0 = disabled
    max_turns: int = 0  # 0 = unlimited


class SessionLifecycle:
    """Checks whether a session should be reset based on policy."""

    def __init__(self, policy: Optional[SessionPolicy] = None):
        self.policy = policy or SessionPolicy()

    def should_reset(
        self,
        last_active_at: Optional[datetime],
        turn_count: int = 0,
        created_at: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        """
        Check if a session should be reset.

        Returns:
            (should_reset, reason) tuple
        """
        now = datetime.now(timezone.utc)

        # Daily reset
        if self.policy.daily_reset_hour and last_active_at:
            last_active = (
                last_active_at
                if last_active_at.tzinfo
                else last_active_at.replace(tzinfo=timezone.utc)
            )

            # Was the last activity before today's reset boundary?
            today_reset = now.replace(
                hour=self.policy.daily_reset_hour, minute=0, second=0, microsecond=0
            )
            if now >= today_reset and last_active < today_reset:
                return True, f"daily reset ({self.policy.daily_reset_hour}:00 UTC)"

        # Idle timeout
        if self.policy.idle_timeout_minutes and last_active_at:
            last_active = (
                last_active_at
                if last_active_at.tzinfo
                else last_active_at.replace(tzinfo=timezone.utc)
            )
            idle = now - last_active
            if idle > timedelta(minutes=self.policy.idle_timeout_minutes):
                return (
                    True,
                    f"idle {int(idle.total_seconds() // 60)}m (limit: {self.policy.idle_timeout_minutes}m)",
                )

        # Max turns
        if self.policy.max_turns and turn_count >= self.policy.max_turns:
            return True, f"reached {turn_count}/{self.policy.max_turns} turns"

        return False, ""

    @staticmethod
    def get_session_key(
        platform: str,
        sender_id: str,
        thread_id: Optional[str] = None,
    ) -> str:
        """
        Generate a canonical session key.

        Maps different communication patterns to session keys:
        - DM: platform-sender_id
        - Thread: platform-sender_id-thread_id
        """
        key = f"{platform}-{sender_id}"
        if thread_id:
            key += f"-{thread_id}"
        return key
