"""
Global registry tracking active streaming sessions.

Extracted from streaming.py so that other modules (heartbeat, scheduler)
can check for active streams without importing the full streaming module.
"""

import asyncio
from typing import Dict


class StreamControl:
    """Holds cooperative cancellation state for an active stream."""

    __slots__ = ("cancel_event", "reason")

    def __init__(self):
        self.cancel_event = asyncio.Event()
        self.reason = "Stream stopped by user"


# Global registry of active streams: chat_id -> StreamControl
stream_controls: Dict[str, StreamControl] = {}


def stop_stream(chat_id: str, reason: str = "Stream stopped by user") -> bool:
    """Request to stop an active stream."""
    control = stream_controls.get(chat_id)
    if not control:
        return False
    control.reason = reason
    control.cancel_event.set()
    return True
