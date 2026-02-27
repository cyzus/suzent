"""
Streaming module for handling pydantic-ai agent response streaming with SSE.

This module provides functionality for streaming agent responses to clients
using Server-Sent Events (SSE), including:
- Async streaming via pydantic-ai's run_stream_events()
- Tool call and result events streamed in real time
- Text deltas assembled from PartStartEvent / PartDeltaEvent
- Event formatting compatible with the existing frontend
- Plan watching and updates
- Cooperative cancellation
"""

import asyncio
import json
import traceback
from typing import Optional, Dict, Any, AsyncGenerator

from pydantic_ai import (
    Agent,
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
)
from pydantic_ai.run import AgentRunResultEvent

from suzent.core.agent_deps import AgentDeps
from suzent.plan import read_plan_from_database, plan_to_dict, auto_complete_current
from loguru import logger


class StreamControl:
    """Holds cooperative cancellation state for an active stream."""

    __slots__ = ("cancel_event", "reason")

    def __init__(self):
        self.cancel_event = asyncio.Event()
        self.reason = "Stream stopped by user"


# Global registry of active streams
stream_controls: Dict[str, StreamControl] = {}


def _plan_snapshot(chat_id: Optional[str] = None) -> dict:
    """Get a snapshot of the current plan state."""
    try:
        if not chat_id:
            return {"objective": "", "tasks": []}
        plan = read_plan_from_database(chat_id)
        if not plan:
            return {"objective": "", "phases": []}
        return plan_to_dict(plan) or {"objective": "", "phases": []}
    except Exception:
        return {"objective": "", "tasks": []}


async def stream_agent_responses(
    agent: Agent[AgentDeps, str],
    message: str | list,
    deps: AgentDeps,
    message_history: list | None = None,
    chat_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Runs the pydantic-ai agent with streaming and yields JSON-formatted SSE events.

    Uses ``run_stream_events()`` which yields all events (tool calls, tool
    results, text deltas, final result) as they happen — no blocking.

    Args:
        agent: The pydantic-ai Agent instance.
        message: User message (string or list for multimodal).
        deps: AgentDeps dependency container.
        message_history: Previous message history for conversation continuity.
        chat_id: Optional chat identifier for plan tracking.

    Yields:
        Server-sent event strings in the format ``data: {json}\\n\\n``
    """
    control = StreamControl()
    if chat_id:
        stream_controls[chat_id] = control

    # Plan watcher task
    plan_queue: asyncio.Queue = asyncio.Queue()
    stop_plan_watcher = asyncio.Event()

    async def plan_watcher(interval: float = 0.7):
        last_snapshot = None
        try:
            while not stop_plan_watcher.is_set():
                await asyncio.sleep(interval)
                if control.cancel_event.is_set():
                    break
                try:
                    snapshot = _plan_snapshot(chat_id)
                    if snapshot != last_snapshot:
                        last_snapshot = snapshot
                        await plan_queue.put(snapshot)
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    watcher_task = asyncio.create_task(plan_watcher()) if chat_id else None

    # Accumulate full text for final_answer
    full_text_parts: list[str] = []
    result_output = None

    try:
        # --- Build run kwargs ---
        run_kwargs: Dict[str, Any] = {"deps": deps}
        if message_history:
            run_kwargs["message_history"] = message_history

        # --- Stream with run_stream_events (real-time, non-blocking) ---
        async with agent:  # MCP server context management
            async for event in agent.run_stream_events(message, **run_kwargs):
                if control.cancel_event.is_set():
                    yield _sse({"type": "stopped", "data": {"reason": control.reason}})
                    break

                # --- AgentRunResultEvent: final result with all messages ---
                if isinstance(event, AgentRunResultEvent):
                    result_output = event.result
                    # Store messages for caller to persist state
                    try:
                        agent._last_messages = event.result.all_messages()  # type: ignore[attr-defined]
                    except Exception:
                        agent._last_messages = []  # type: ignore[attr-defined]
                    continue

                # --- Map pydantic-ai events to SSE ---
                sse = _map_event(event, full_text_parts)
                if sse is not None:
                    yield _sse(sse)

                # Drain plan updates
                while not plan_queue.empty():
                    try:
                        snapshot = plan_queue.get_nowait()
                        yield _sse({"type": "plan_refresh", "data": snapshot})
                    except asyncio.QueueEmpty:
                        break

        # --- After stream completes ---
        if not control.cancel_event.is_set():
            # Emit final answer
            final_text = result_output.output if result_output else "".join(full_text_parts)
            if final_text:
                yield _sse({"type": "final_answer", "data": str(final_text)})

            # Final plan refresh
            if chat_id:
                yield _sse({"type": "plan_refresh", "data": _plan_snapshot(chat_id)})

    except Exception as e:
        if not control.cancel_event.is_set():
            logger.error(f"Streaming error: {e}\n{traceback.format_exc()}")
            yield _sse({"type": "error", "data": str(e)})

    finally:
        stop_plan_watcher.set()
        if watcher_task:
            watcher_task.cancel()
            try:
                await watcher_task
            except (asyncio.CancelledError, Exception):
                pass

        if chat_id:
            if not control.cancel_event.is_set():
                try:
                    auto_complete_current(chat_id)
                except Exception as e:
                    logger.debug(f"Failed to auto-complete plan: {e}")

            existing = stream_controls.get(chat_id)
            if existing is control:
                stream_controls.pop(chat_id, None)


# ─── Event mapping ─────────────────────────────────────────────────────


def _map_event(event, full_text_parts: list[str]) -> dict | None:
    """Map a pydantic-ai event to a suzent SSE event dict.

    Returns None for events we don't need to forward to the frontend.
    """

    # ── Text streaming (PartStartEvent with TextPart) ──
    if isinstance(event, PartStartEvent):
        from pydantic_ai.messages import TextPart, ToolCallPart
        if isinstance(event.part, TextPart) and event.part.content:
            full_text_parts.append(event.part.content)
            return {"type": "stream_delta", "data": {"content": event.part.content}}
        # We don't emit ToolCallPart starts — we wait for FunctionToolCallEvent
        return None

    # ── Text delta ──
    if isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta):
            full_text_parts.append(event.delta.content_delta)
            return {"type": "stream_delta", "data": {"content": event.delta.content_delta}}
        return None

    # ── Tool call started ──
    if isinstance(event, FunctionToolCallEvent):
        return {
            "type": "action",
            "data": {
                "tool_calls": [{
                    "name": event.part.tool_name,
                    "arguments": event.part.args if isinstance(event.part.args, dict) else {},
                    "id": event.part.tool_call_id or "",
                }],
            },
        }

    # ── Tool call finished ──
    if isinstance(event, FunctionToolResultEvent):
        try:
            output_str = str(event.result.content)[:2000] if event.result else ""
            tool_name = getattr(event.result, "tool_name", "")
        except Exception:
            output_str = ""
            tool_name = ""
        return {
            "type": "tool_output",
            "data": {
                "tool_name": tool_name,
                "output": output_str,
                "tool_call_id": event.tool_call_id or "",
            },
        }

    # ── Final result marker ──
    if isinstance(event, FinalResultEvent):
        return {
            "type": "final_result_marker",
            "data": {"tool_name": event.tool_name},
        }

    return None


def _sse(event: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


def stop_stream(chat_id: str, reason: str = "Stream stopped by user") -> bool:
    """Request to stop an active stream."""
    control = stream_controls.get(chat_id)
    if not control:
        return False
    control.reason = reason
    control.cancel_event.set()
    return True
