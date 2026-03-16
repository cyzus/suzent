"""
Global registry tracking active streaming sessions.

Extracted from streaming.py so that other modules (heartbeat, scheduler)
can check for active streams without importing the full streaming module.
"""

import asyncio
from typing import Dict


class StreamControl:
    """Holds cooperative cancellation state for an active stream."""

    __slots__ = ("cancel_event", "completed_event", "reason")

    def __init__(self):
        self.cancel_event = asyncio.Event()
        self.completed_event = asyncio.Event()  # Set when post-processing finishes
        self.reason = "Stream stopped by user"


# Global registry of active streams: chat_id -> StreamControl
stream_controls: Dict[str, StreamControl] = {}

# Cache policy-decided approvals for suspended streams so resume payloads
# can merge explicit user decisions with backend auto-decisions.
pending_auto_approvals: Dict[str, Dict[str, bool]] = {}


def stop_stream(chat_id: str, reason: str = "Stream stopped by user") -> bool:
    """Request to stop an active stream."""
    control = stream_controls.get(chat_id)
    if not control:
        return False
    control.reason = reason
    control.cancel_event.set()
    return True


def merge_pending_auto_approvals(chat_id: str, approvals: Dict[str, bool]) -> None:
    """Merge auto-approval decisions for a chat into the pending cache."""
    if not chat_id or not approvals:
        return
    existing = pending_auto_approvals.get(chat_id, {})
    existing.update(approvals)
    pending_auto_approvals[chat_id] = existing


def pop_pending_auto_approvals(chat_id: str) -> Dict[str, bool]:
    """Return and clear cached auto-approvals for a chat."""
    if not chat_id:
        return {}
    return pending_auto_approvals.pop(chat_id, {})
