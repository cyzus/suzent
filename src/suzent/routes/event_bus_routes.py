"""
Event bus SSE endpoint.

GET /events/stream

A single persistent SSE connection that multiplexes every background stream
(heartbeat, cron/scheduler, social, subagents, wakeup turns) into one channel.
The client subscribes once and receives tagged events for all sessions instead
of opening a separate /chat/live connection per background chat.

Event shapes (JSON in the SSE data field):
  {"event": "snapshot",      "streams": ["chat-id-1", ...]}   # sent immediately on connect
  {"event": "stream_started","chat_id": "..."}
  {"event": "chunk",         "chat_id": "...", "data": "<raw SSE string>"}
  {"event": "stream_ended",  "chat_id": "..."}

The frontend can reconstruct any background stream's content by collecting
"chunk" events for a given chat_id and parsing the embedded "data" strings
exactly as it would parse a /chat/live SSE stream.
"""

import asyncio
import json

from starlette.requests import Request
from starlette.responses import StreamingResponse

from suzent.core.stream_registry import (
    background_queues,
    register_bus_subscriber,
    unregister_bus_subscriber,
)


async def event_bus_stream(request: Request) -> StreamingResponse:
    """Persistent SSE multiplexer for all background streams."""

    async def generate():
        q = register_bus_subscriber()
        try:
            # Snapshot: tell the client which background streams are already running
            active = list(background_queues.keys())
            yield f"data: {json.dumps({'event': 'snapshot', 'streams': active})}\n\n"

            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister_bus_subscriber(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
