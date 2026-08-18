"""Small state machine used by the service memory watchdog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceGuard:
    max_rss_bytes: int
    consecutive_limit: int = 5
    consecutive_over_limit: int = 0

    def observe(self, rss_bytes: int) -> bool:
        """Return True once the process stays over its limit long enough."""
        if rss_bytes > self.max_rss_bytes:
            self.consecutive_over_limit += 1
        else:
            self.consecutive_over_limit = 0
        return self.consecutive_over_limit >= self.consecutive_limit
