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
    
    # State for accumulating tool calls across deltas
    tool_names: Dict[str, str] = {}
    tool_args: Dict[str, str] = {}
    emitted_tool_calls: set[str] = set()

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
                        
                    # Emit the final text immediately upon receiving the result event
                    final_text = getattr(result_output, "data", "") if result_output else ""
                    if not full_text_parts and final_text:
                        yield _sse({"type": "final_answer", "data": str(final_text)})
                        
                    continue

                # --- Map pydantic-ai events to SSE ---
                sse = _map_event(event, full_text_parts, tool_names, tool_args, emitted_tool_calls)
                if sse is not None:
                    if isinstance(sse, list):
                        for s in sse:
                            yield _sse(s)
                    else:
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


def _map_event(
    event, full_text_parts: list[str], tool_names: Dict[str, str], tool_args: Dict[str, str], emitted_tool_calls: set[str]
) -> dict | None:
    """Map a pydantic-ai event to a suzent SSE event dict.

    Returns None for events we don't need to forward to the frontend.
    """
    import json

    # ── Text streaming (PartStartEvent with TextPart) ──
    if isinstance(event, PartStartEvent):
        from pydantic_ai.messages import TextPart, ToolCallPart
        if isinstance(event.part, TextPart) and event.part.content:
            content = event.part.content
            # Gemini occasionally prints its tools state inside the output text directly
            if "<details>" in content and "web_search" in content:
                content = content.split("<details>")[0]
            if content.strip():
                full_text_parts.append(content)
                return {"type": "stream_delta", "data": {"content": content}}
            return None
        
        # Emit early tool action so UI knows which tool is being called
        if isinstance(event.part, ToolCallPart):
            name = getattr(event.part, "tool_name", "")
            tc_id = getattr(event.part, "tool_call_id", "")
            args = getattr(event.part, "args", {})
            if not isinstance(args, dict):
                args = {}
                
            if name and tc_id and tc_id not in emitted_tool_calls:
                emitted_tool_calls.add(tc_id)
                tool_args[tc_id] = json.dumps(args) if args else "{}"
                return {
                    "type": "stream_delta",
                    "data": {
                        "tool_calls": [{
                            "name": name,
                            "arguments": args,
                            "id": tc_id,
                        }],
                    },
                }
        return None

    # ── Text delta ──
    if isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta):
            content_delta = event.delta.content_delta
            # Filter injected html streams
            if "<details>" in content_delta or "<summary>" in content_delta:
                return None
            full_text_parts.append(content_delta)
            return {"type": "stream_delta", "data": {"content": content_delta}}
            
        from pydantic_ai.messages import ToolCallPartDelta
        if isinstance(event.delta, ToolCallPartDelta):
            tc_id = getattr(event.delta, "tool_call_id", "")
            if tc_id:
                name_delta = getattr(event.delta, "tool_name_delta", "")
                args_delta = getattr(event.delta, "args_delta", "")
                
                if name_delta:
                    tool_names[tc_id] = tool_names.get(tc_id, "") + name_delta
                
                has_new_args = False
                if args_delta:
                    current_args = tool_args.get(tc_id, "")
                    if isinstance(args_delta, str):
                        tool_args[tc_id] = current_args + args_delta
                    elif isinstance(args_delta, dict):
                        # Pydantic AI occasionally sends dict deltas depending on the model/provider
                        try:
                            if not current_args:
                                current_args = "{}"
                            curr = json.loads(current_args)
                            curr.update(args_delta)
                            tool_args[tc_id] = json.dumps(curr)
                        except Exception:
                            tool_args[tc_id] = json.dumps(args_delta)
                    # If this isn't strictly the first emission, always send argument updates!
                    has_new_args = True
                    
                current_name = tool_names.get(tc_id, "")
                
                # Emit if we have a new args delta OR if we haven't emitted this tool call name yet
                if current_name and (has_new_args or tc_id not in emitted_tool_calls):
                    emitted_tool_calls.add(tc_id)
                    current_arguments = tool_args.get(tc_id, "")
                    return {
                        "type": "stream_delta",
                        "data": {
                            "tool_calls": [{
                                "name": current_name,
                                "arguments": current_arguments,
                                "id": tc_id,
                            }],
                        },
                    }
        return None

    # ── Tool call started ──
    if isinstance(event, FunctionToolCallEvent):
        tc_id = getattr(event.part, "tool_call_id", "")
        events = []
        name = getattr(event.part, "tool_name", "")
        args = getattr(event.part, "args", {})
        if not isinstance(args, dict):
            args = {}
            
        # If the provider doesn't stream deltas (e.g., Gemini), we must emit the full tool call here
        if tc_id and tc_id not in emitted_tool_calls:
            emitted_tool_calls.add(tc_id)
            events.append({
                "type": "stream_delta",
                "data": {
                    "tool_calls": [{
                        "name": name,
                        "arguments": args,
                        "id": tc_id,
                    }],
                },
            })
            
        events.append({
            "type": "action",
            "data": {
                "tool_calls": [{
                    "name": name,
                    "arguments": args,
                    "id": tc_id,
                }],
            },
        })
        return events

    # ── Tool call finished ──
    if isinstance(event, FunctionToolResultEvent):
        try:
            output_str = str(event.result.content)[:2000] if getattr(event, "result", None) else ""
            tool_name = getattr(event.result, "tool_name", "") if getattr(event, "result", None) else getattr(event, "tool_name", "")
            tc_id = getattr(event.result, "tool_call_id", "") if getattr(event, "result", None) else ""
            if not tc_id:
                tc_id = getattr(event, "tool_call_id", "")
        except Exception:
            output_str = ""
            tool_name = ""
            tc_id = getattr(event, "tool_call_id", "")
            
        return {
            "type": "tool_output",
            "data": {
                "tool_name": tool_name,
                "output": output_str,
                "tool_call_id": tc_id or "",
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
