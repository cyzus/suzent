"""
Streaming module for handling pydantic-ai agent response streaming with SSE.

This module provides functionality for streaming agent responses to clients
using Server-Sent Events (SSE), including:
- Async streaming via pydantic-ai's run_stream_events()
- Tool call and result events streamed in real time
- Text deltas assembled from PartStartEvent / PartDeltaEvent
- Human-in-the-loop (HITL) tool approval via pydantic-ai deferred tools
- Event formatting compatible with the AG-UI protocol
- Plan watching and updates
- Cooperative cancellation
"""

import asyncio
import traceback
import uuid
from typing import Optional, Dict, Any, AsyncGenerator

from pydantic_ai import (
    Agent,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from pydantic_ai.ui.ag_ui._event_stream import AGUIEventStream
from ag_ui.core import RunAgentInput, CustomEvent, RunErrorEvent
from ag_ui.encoder import EventEncoder

from suzent.core.agent_deps import AgentDeps
from suzent.plan import read_plan_from_database, plan_to_dict, auto_complete_current
from loguru import logger


# Module-level encoder for custom events
_encoder = EventEncoder()


def _encode_custom(name: str, value: Any) -> str:
    """Encode a custom AG-UI event as an SSE string."""
    return _encoder.encode(CustomEvent(name=name, value=value))


class StreamControl:
    """Holds cooperative cancellation state for an active stream."""

    __slots__ = ("cancel_event", "reason")

    def __init__(self):
        self.cancel_event = asyncio.Event()
        self.reason = "Stream stopped by user"


# Global registry of active streams and deps (for HITL approval endpoint)
stream_controls: Dict[str, StreamControl] = {}
active_deps: Dict[str, AgentDeps] = {}


def _plan_snapshot(chat_id: Optional[str] = None) -> dict:
    """Get a snapshot of the current plan state."""
    try:
        if not chat_id:
            return {"objective": "", "phases": []}
        plan = read_plan_from_database(chat_id)
        if not plan:
            return {"objective": "", "phases": []}
        return plan_to_dict(plan) or {"objective": "", "phases": []}
    except Exception:
        return {"objective": "", "phases": []}


def _safe_args_preview(args: Any, max_len: int = 500) -> dict:
    """Truncate large arg values for the approval dialog."""
    if not isinstance(args, dict):
        return {}
    preview = {}
    for k, v in args.items():
        if v is None:
            continue
        s = str(v)
        preview[k] = (s[:max_len] + "\u2026") if len(s) > max_len else s
    return preview


async def _collect_approvals(
    deps: AgentDeps,
    approvals: list,
    sse_queue: asyncio.Queue,
    cancel_event: asyncio.Event,
    chat_id: Optional[str],
) -> Optional[DeferredToolResults]:
    """Emit approval requests, collect user responses, return DeferredToolResults.

    Returns None if cancelled during the wait.
    """
    results: Dict[str, Any] = {}

    for tc in approvals:
        # Check session policy first
        policy = deps.tool_approval_policy.get(tc.tool_name)
        if policy == "always_allow":
            results[tc.tool_call_id] = True
            continue
        if policy == "always_deny":
            results[tc.tool_call_id] = False
            continue

        # Need user approval — register pending and emit SSE event
        evt = asyncio.Event()
        deps.pending_approvals[tc.tool_call_id] = {
            "event": evt,
            "approved": None,
            "tool_name": tc.tool_name,
        }

        # Get args as dict for preview
        try:
            args_dict = tc.args if isinstance(tc.args, dict) else {}
        except Exception:
            args_dict = {}

        await sse_queue.put(
            (
                "approval",
                {
                    "request_id": tc.tool_call_id,
                    "tool_name": tc.tool_name,
                    "tool_call_id": tc.tool_call_id,
                    "args": _safe_args_preview(args_dict),
                },
            )
        )

    # Wait for all pending user approvals
    for tc_id in list(deps.pending_approvals.keys()):
        if tc_id in results:
            continue  # already resolved by policy

        data = deps.pending_approvals.get(tc_id)
        if not data:
            continue

        # Wait for this approval or cancellation
        approval_evt = data["event"]
        cancel_task = asyncio.create_task(cancel_event.wait())
        approval_task = asyncio.create_task(approval_evt.wait())
        done, pending = await asyncio.wait(
            [cancel_task, approval_task],
            timeout=300,  # 5 min timeout
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

        if cancel_event.is_set():
            deps.pending_approvals.clear()
            return None

        # Timed out
        if not approval_evt.is_set():
            results[tc_id] = False
            continue

        result = deps.pending_approvals.get(tc_id, {})
        approved = bool(result.get("approved"))
        results[tc_id] = approved

        # Handle "remember" for session policy
        remember = result.get("remember")
        tool_name = result.get("tool_name", "")
        if remember == "session" and tool_name:
            deps.tool_approval_policy[tool_name] = (
                "always_allow" if approved else "always_deny"
            )

    deps.pending_approvals.clear()
    return DeferredToolResults(approvals=results)


async def stream_agent_responses(
    agent: Agent,
    message: str | list,
    deps: AgentDeps,
    message_history: list | None = None,
    chat_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Runs the pydantic-ai agent with streaming and yields AG-UI formatted events.

    Uses a queue-based architecture: the agent runs in a background task so
    the generator can yield both regular events and HITL approval requests.
    HITL is handled via pydantic-ai native deferred tools — the agent run
    stops when approval is needed and restarts after the user responds.

    Yields:
        Server-sent event strings in AG-UI protocol format (data: {json}\n\n)
    """
    control = StreamControl()
    if chat_id:
        stream_controls[chat_id] = control

    # Wire HITL fields into deps
    sse_queue: asyncio.Queue = asyncio.Queue()
    deps.cancel_event = control.cancel_event
    if chat_id:
        active_deps[chat_id] = deps

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

    # History tracker for cancellation recovery
    partial_history = list(message_history) if message_history else []

    out_queue: asyncio.Queue = asyncio.Queue()

    # --- Background agent runner with deferred-tool loop ---
    async def _agent_runner():
        """Run the agent in a background task, looping for deferred tool approvals."""
        prompt = message
        history = list(message_history) if message_history else None
        deferred_results = None

        try:
            async with agent:  # MCP server context management
                while not control.cancel_event.is_set():
                    run_kwargs: Dict[str, Any] = {"deps": deps}
                    if history:
                        run_kwargs["message_history"] = history
                    if deferred_results:
                        run_kwargs["deferred_tool_results"] = deferred_results

                    last_result_event = None
                    async for event in agent.run_stream_events(
                        prompt, **run_kwargs
                    ):
                        if control.cancel_event.is_set():
                            break
                        logger.debug(
                            f"[Streaming] Received event from agent: {type(event).__name__}"
                        )
                        if isinstance(event, AgentRunResultEvent):
                            last_result_event = event
                        await sse_queue.put(("event", event))

                    # Check if deferred tools need approval
                    if (
                        last_result_event
                        and isinstance(
                            last_result_event.result.output, DeferredToolRequests
                        )
                    ):
                        deferred = last_result_event.result.output
                        if deferred.approvals:
                            deferred_results = await _collect_approvals(
                                deps,
                                deferred.approvals,
                                sse_queue,
                                control.cancel_event,
                                chat_id,
                            )
                            if deferred_results is None:
                                break  # cancelled
                            history = last_result_event.result.all_messages()
                            prompt = None  # no new user prompt on resume
                            continue

                    break  # normal completion

        except Exception as e:
            await sse_queue.put(("error", e))
        finally:
            await sse_queue.put(("done", None))

    agent_task = asyncio.create_task(_agent_runner())

    # --- Native stream generator that feeds AGUIEventStream ---
    async def native_stream_generator():
        while True:
            # Drain plan updates as AG-UI CustomEvent
            while not plan_queue.empty():
                try:
                    snapshot = plan_queue.get_nowait()
                    await out_queue.put(
                        ("chunk", _encode_custom("plan_refresh", snapshot))
                    )
                except asyncio.QueueEmpty:
                    break

            try:
                msg = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
                msg_type, payload = msg

                if msg_type == "event":
                    # Track history manually for cancellation recovery
                    try:
                        from pydantic_ai.messages import (
                            RunRequestEvent,
                            RunResponseEvent,
                        )

                        if isinstance(payload, RunRequestEvent):
                            partial_history.append(payload.request)
                        elif isinstance(payload, RunResponseEvent):
                            partial_history.append(payload.response)
                    except Exception:
                        pass

                    # AgentRunResultEvent: final result with all messages
                    if isinstance(payload, AgentRunResultEvent):
                        try:
                            # Extract usage data
                            usage = payload.result.usage()
                            usage_data = {
                                "input_tokens": usage.request_tokens,
                                "output_tokens": usage.response_tokens,
                                "total_tokens": usage.total_tokens,
                                "details": usage.details,
                            }
                            await out_queue.put(
                                ("chunk", _encode_custom("usage_update", usage_data))
                            )

                            agent._last_messages = payload.result.all_messages()  # type: ignore[attr-defined]
                        except Exception:
                            agent._last_messages = []

                    yield payload

                elif msg_type == "approval":
                    # HITL: emit as AG-UI CustomEvent with all approval info
                    await out_queue.put(
                        (
                            "chunk",
                            _encode_custom(
                                "tool_approval_request",
                                {
                                    "approvalId": payload["request_id"],
                                    "toolCallId": payload.get("tool_call_id")
                                    or payload["request_id"],
                                    "toolName": payload.get("tool_name", ""),
                                    "args": payload.get("args", {}),
                                    "chatId": chat_id,
                                },
                            ),
                        )
                    )

                elif msg_type == "done":
                    break

                elif msg_type == "error":
                    err = RunErrorEvent(message=str(payload))
                    await out_queue.put(("chunk", _encoder.encode(err)))
                    break

            except asyncio.TimeoutError:
                if control.cancel_event.is_set():
                    break

    # --- Background worker to encode stream using AGUIEventStream ---
    async def encode_worker():
        try:
            run_input = RunAgentInput(
                thread_id=chat_id or "default",
                run_id=str(uuid.uuid4()),
                messages=[],
                state=None,
                tools=[],
                context=[],
                forwarded_props=None,
            )
            event_stream = AGUIEventStream(run_input)
            agui_events = event_stream.transform_stream(native_stream_generator())
            async for agui_event in agui_events:
                if control.cancel_event.is_set():
                    break
                encoded = event_stream.encode_event(agui_event)
                await out_queue.put(("chunk", encoded))
        except Exception as e:
            err = RunErrorEvent(message=str(e))
            await out_queue.put(("chunk", _encoder.encode(err)))
        finally:
            await out_queue.put(("done", None))

    encode_task = asyncio.create_task(encode_worker())

    try:
        while True:
            try:
                msg = await asyncio.wait_for(out_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if control.cancel_event.is_set():
                    err = RunErrorEvent(message="Stream stopped by user")
                    yield _encoder.encode(err)
                    break
                continue

            msg_type, payload = msg
            if msg_type == "chunk":
                yield payload
            elif msg_type == "done":
                break

        # --- After stream completes ---
        if not control.cancel_event.is_set() and chat_id:
            yield _encode_custom("plan_refresh", _plan_snapshot(chat_id))

    except Exception as e:
        if not control.cancel_event.is_set():
            logger.error(f"Streaming error: {e}\n{traceback.format_exc()}")
            err = RunErrorEvent(message=str(e))
            yield _encoder.encode(err)

    finally:
        # Cancel background tasks
        for task in (agent_task, encode_task):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        # Handle cancellation by preserving partial history
        if control.cancel_event.is_set():
            try:
                agent._last_messages = partial_history
            except Exception as e:
                logger.error(f"Failed to reconstruct partial history on cancel: {e}")

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
            active_deps.pop(chat_id, None)

        # Unblock any tools still waiting for approval
        for req_id, req_data in list(deps.pending_approvals.items()):
            evt = req_data.get("event")
            if evt and not evt.is_set():
                req_data["approved"] = False
                evt.set()
        deps.pending_approvals.clear()


def stop_stream(chat_id: str, reason: str = "Stream stopped by user") -> bool:
    """Request to stop an active stream."""
    control = stream_controls.get(chat_id)
    if not control:
        return False
    control.reason = reason
    control.cancel_event.set()
    return True


def resolve_tool_approval(
    chat_id: str,
    request_id: str,
    approved: bool,
    remember: Optional[str] = None,
) -> bool:
    """Resolve a pending tool approval request.

    Args:
        chat_id: The chat session identifier.
        request_id: The tool_call_id from the approval request.
        approved: Whether the user approved the tool execution.
        remember: Optional "session" to remember the decision.
    """
    deps = active_deps.get(chat_id)
    if not deps:
        return False

    req = deps.pending_approvals.get(request_id)
    if not req:
        return False

    req["approved"] = approved
    req["remember"] = remember
    evt = req.get("event")
    if evt:
        evt.set()

    return True
