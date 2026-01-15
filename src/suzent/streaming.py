"""
Streaming module for handling agent response streaming with SSE.

This module provides functionality for streaming agent responses to clients
using Server-Sent Events (SSE), including:
- Stream control for cooperative cancellation
- Event formatting and serialization
- Plan watching and updates
- Background processing with asyncio
"""

import asyncio
import contextlib
import json
import threading
from typing import Optional, Dict, AsyncGenerator

from smolagents.agents import ActionOutput, PlanningStep, ToolOutput
from smolagents.memory import ActionStep, FinalAnswerStep
from smolagents.models import ChatMessageStreamDelta

from suzent.plan import read_plan_from_database, plan_to_dict, auto_complete_current
from suzent.utils import to_serializable


class StreamControl:
    """Holds cooperative cancellation state for an active stream."""

    __slots__ = ("async_event", "thread_event", "reason")

    def __init__(self, async_event: asyncio.Event, thread_event: threading.Event):
        """
        Initialize stream control.
        
        Args:
            async_event: Asyncio event for async cancellation.
            thread_event: Threading event for thread-based cancellation.
        """
        self.async_event = async_event
        self.thread_event = thread_event
        self.reason = "Stream stopped by user"


# Global registry of active streams
stream_controls: Dict[str, StreamControl] = {}


def step_to_json_event(chunk) -> Optional[dict]:
    """
    Converts an agent's step into a JSON event dictionary.
    
    Args:
        chunk: Agent step or output chunk to convert.
    
    Returns:
        Dictionary with 'type' and 'data' keys, or None if not serializable.
    """
    event_map = {
        ActionStep: "action",
        PlanningStep: "planning",
        FinalAnswerStep: "final_answer",
        ChatMessageStreamDelta: "stream_delta",
        ActionOutput: "action_output",
        ToolOutput: "tool_output",
    }
    event_type = next(
        (event_map[t] for t in event_map if isinstance(chunk, t)), "other"
    )

    if event_type == "final_answer":
        output = getattr(chunk, "output", str(chunk))
        data = (
            output.to_string()
            if hasattr(output, "to_string") and not isinstance(output, str)
            else str(output)
        )
    elif event_type == "action_output" and chunk.output is None:
        return None
    elif event_type == "tool_output":
        # Handle ToolOutput specifically to ensure all fields are serialized
        data = to_serializable(chunk)
    elif event_type == "action":
        # Handle ActionStep specially to deal with error field
        # ActionStep may contain an AgentError which has non-serializable logger
        data = _serialize_action_step(chunk)
    else:
        data = to_serializable(chunk)

    return {"type": event_type, "data": data}


def _serialize_action_step(action_step) -> dict:
    """
    Safely serialize an ActionStep, handling the error field specially.
    
    Args:
        action_step: ActionStep instance to serialize.
    
    Returns:
        Dictionary with serializable ActionStep data.
    """
    try:
        # Get all attributes
        data = {}
        for key, value in action_step.__dict__.items():
            if key.startswith('_'):
                continue
            
            # Handle error field specially
            if key == 'error' and value is not None:
                # Serialize error without the logger
                try:
                    data['error'] = {
                        'type': type(value).__name__,
                        'message': str(value),
                        'args': value.args if hasattr(value, 'args') else []
                    }
                except Exception:
                    data['error'] = str(value)
            else:
                # Try to serialize other fields normally
                try:
                    data[key] = to_serializable(value)
                except Exception:
                    # Skip fields that can't be serialized
                    pass
        
        return data
    except Exception as e:
        # Fallback to basic serialization
        return {'error': f'Failed to serialize ActionStep: {str(e)}'}



def _plan_snapshot(chat_id: Optional[str] = None) -> dict:
    """
    Get a snapshot of the current plan state.
    
    Args:
        chat_id: Chat identifier to get plan for.
    
    Returns:
        Dictionary with 'objective' and 'tasks' keys.
    """
    try:
        if not chat_id:
            return {"objective": "", "tasks": []}
        plan = read_plan_from_database(chat_id)
        if not plan:
            return {"objective": "", "phases": []}
            
        return plan_to_dict(plan) or {"objective": "", "phases": []}
    except Exception:
        return {"objective": "", "tasks": []}


class _PlanTick:
    """Internal marker for plan updates."""
    __slots__ = ["snapshot"]

    def __init__(self, snapshot: dict):
        self.snapshot = snapshot


class _StopSignal:
    """Internal marker for stop requests."""
    __slots__ = ["reason"]

    def __init__(self, reason: str):
        self.reason = reason


async def stream_agent_responses(
    agent,
    message: str,
    reset: bool = False,
    chat_id: Optional[str] = None,
    images: Optional[list] = None
) -> AsyncGenerator[str, None]:
    """
    Runs the agent with the given message and yields JSON-formatted SSE events.

    Uses a background thread + asyncio.Queue so the event loop is not blocked and
    deltas flush to the client sooner. Adds cooperative cancellation so the client
    can request streaming to stop explicitly.

    Args:
        agent: The agent instance to run.
        message: User message to process.
        reset: Whether to reset agent memory before processing.
        chat_id: Optional chat identifier for plan tracking.
        images: Optional list of PIL Image objects for multimodal input.

    Yields:
        Server-sent event strings in the format "data: {json}\n\n"
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    async_stop_event = asyncio.Event()
    thread_stop_event = threading.Event()
    control = StreamControl(async_stop_event, thread_stop_event)

    if chat_id:
        stream_controls[chat_id] = control

    def worker():
        """Background worker that runs agent in thread."""
        stop_notified = False

        def notify_stop():
            nonlocal stop_notified
            if stop_notified:
                return
            stop_notified = True
            reason = control.reason or "Stream stopped by user"
            loop.call_soon_threadsafe(queue.put_nowait, _StopSignal(reason))

        try:
            gen = agent.run(message, stream=True, reset=reset, images=images)
            for chunk in gen:
                if control.thread_event.is_set():
                    notify_stop()
                    break
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            if not control.thread_event.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            if control.thread_event.is_set():
                notify_stop()
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel
            loop.call_soon_threadsafe(async_stop_event.set)

    async def plan_watcher(interval: float = 0.7):
        """Watch the plan for changes and enqueue updates."""
        last_snapshot = None
        try:
            while not async_stop_event.is_set():
                if control.thread_event.is_set():
                    break
                await asyncio.sleep(interval)
                try:
                    snapshot = _plan_snapshot(chat_id)
                    if snapshot != last_snapshot:
                        last_snapshot = snapshot
                        await queue.put(_PlanTick(snapshot))
                except Exception as e:
                    await queue.put(_PlanTick({"error": str(e)}))
        except asyncio.CancelledError:
            pass

    # Start background tasks
    threading.Thread(target=worker, daemon=True).start()
    watcher_task = asyncio.create_task(plan_watcher())

    stop_requested = False

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break

            if isinstance(chunk, _StopSignal):
                stop_requested = True
                stop_payload = {"type": "stopped", "data": {"reason": chunk.reason}}
                yield f"data: {json.dumps(stop_payload)}\n\n"
                await asyncio.sleep(0)
                continue

            if isinstance(chunk, Exception):
                if stop_requested:
                    continue
                error_event = {"type": "error", "data": str(chunk)}
                yield f"data: {json.dumps(error_event)}\n\n"
                await asyncio.sleep(0)
                continue

            if isinstance(chunk, _PlanTick):
                if stop_requested:
                    continue
                try:
                    plan_event = {"type": "plan_refresh", "data": chunk.snapshot}
                    yield f"data: {json.dumps(plan_event)}\n\n"
                except Exception as e:
                    error_event = {"type": "error", "data": f"Plan tick error: {e!s}"}
                    yield f"data: {json.dumps(error_event)}\n\n"
                await asyncio.sleep(0)
                continue

            if stop_requested:
                await asyncio.sleep(0)
                continue

            try:
                json_event = step_to_json_event(chunk)
                if json_event:
                    yield f"data: {json.dumps(json_event)}\n\n"
                    et = json_event.get("type")
                    if et in ("planning", "action"):
                        plan_event = {"type": "plan_refresh", "data": _plan_snapshot(chat_id)}
                        yield f"data: {json.dumps(plan_event)}\n\n"
            except Exception as e:
                # More robust error serialization
                try:
                    error_msg = str(e)
                    chunk_type = type(chunk).__name__ if hasattr(chunk, '__name__') or hasattr(type(chunk), '__name__') else 'unknown'
                    error_event = {"type": "error", "data": f"Serialization error: {error_msg} | Chunk type: {chunk_type}"}
                    yield f"data: {json.dumps(error_event)}\n\n"
                except Exception:
                    # Fallback for complete failure
                    yield 'data: {"type": "error", "data": "Critical serialization failure"}\n\n'

            await asyncio.sleep(0)
    finally:
        async_stop_event.set()
        watcher_task.cancel()
        with contextlib.suppress(Exception):
            await watcher_task

        if chat_id:
            # Auto-complete the current phase if stream finished successfully (not stopped/cancelled)
            if not control.thread_event.is_set():
                try:
                    auto_complete_current(chat_id)
                    # Push final plan update
                    await queue.put(_PlanTick(_plan_snapshot(chat_id)))
                except Exception as e:
                    # Log error but don't fail the stream
                    print(f"Failed to auto-complete plan: {e}")

            existing = stream_controls.get(chat_id)
            if existing is control:
                stream_controls.pop(chat_id, None)


def stop_stream(chat_id: str, reason: str = "Stream stopped by user") -> bool:
    """
    Request to stop an active stream.
    
    Args:
        chat_id: Chat identifier for the stream to stop.
        reason: Reason for stopping the stream.
    
    Returns:
        True if stream was found and stop requested, False otherwise.
    """
    control = stream_controls.get(chat_id)
    if not control:
        return False
    
    control.reason = reason
    control.thread_event.set()
    control.async_event.set()
    return True
