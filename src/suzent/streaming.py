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
import json
import traceback
import uuid
from typing import Optional, Dict, Any, AsyncGenerator

from pydantic_ai import (
    Agent,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from pydantic_ai.ui.ag_ui._event_stream import AGUIEventStream
from ag_ui.core import (
    RunAgentInput,
    CustomEvent,
    RunErrorEvent,
)
from ag_ui.encoder import EventEncoder

from suzent.core.agent_deps import AgentDeps
from suzent.core.stream_registry import (
    StreamControl,
    stream_controls,
    stop_stream,  # noqa: F401 — re-export for backwards compat
    merge_pending_auto_approvals,
    pop_pending_auto_approvals,
    register_active_stream,
    unregister_active_stream,
)
from loguru import logger


# Module-level encoder for custom events
_encoder = EventEncoder()
_FIRST_STREAM_EVENT_TIMEOUT_SECONDS = 45.0
_STREAM_IDLE_TIMEOUT_SECONDS = 120.0
_DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS = 60.0
_AUTO_TITLE_PLACEHOLDER_TITLES = frozenset({"", "new chat", "untitled"})


def _should_generate_auto_title(chat: Any) -> bool:
    """Generate when first turn or when a previous placeholder title survived."""
    if chat is None:
        return False
    turn_count = getattr(chat, "turn_count", 0) or 0
    if turn_count == 0:
        return True
    title = str(getattr(chat, "title", "") or "").strip().lower()
    return title in _AUTO_TITLE_PLACEHOLDER_TITLES


def _serialize_tool_output(output: Any) -> str:
    if isinstance(output, dict):
        return json.dumps(output, ensure_ascii=False)
    if hasattr(output, "model_dump"):
        try:
            return json.dumps(output.model_dump(mode="json"), ensure_ascii=False)
        except Exception:
            return str(output)
    return str(output) if output else ""


def _encode_custom(name: str, value: Any) -> str:
    """Encode a custom AG-UI event as an SSE string."""
    return _encoder.encode(CustomEvent(name=name, value=value))


def _tool_timeout_from_event(event: Any) -> float:
    """Return a stream wait timeout while pydantic-ai is executing a tool."""
    timeout = _DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS
    part = getattr(event, "part", None)
    tool_name = getattr(part, "tool_name", "")
    if tool_name not in ("bash_execute", "BashTool"):
        return timeout

    args = getattr(part, "args", None)
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = None
    if not isinstance(args, dict):
        args = {}
    from suzent.tools.shell.bash_tool import BashTool

    return BashTool.stream_wait_timeout_seconds(args.get("timeout"))


async def _iter_stream_events_with_timeout(
    agent: Any,
    prompt: Any,
    run_kwargs: Dict[str, Any],
) -> AsyncGenerator[Any, None]:
    """Yield stream events, failing fast if the provider never produces one."""
    stream = agent.run_stream_events(prompt, **run_kwargs)
    first_event = True
    tool_calls_in_flight = 0
    tool_wait_timeout = 0.0
    try:
        while True:
            if first_event:
                timeout = _FIRST_STREAM_EVENT_TIMEOUT_SECONDS
                phase = "first event"
            elif tool_calls_in_flight > 0:
                timeout = (
                    tool_wait_timeout or _DEFAULT_TOOL_STREAM_EVENT_TIMEOUT_SECONDS
                )
                phase = "tool result"
            else:
                timeout = _STREAM_IDLE_TIMEOUT_SECONDS
                phase = "next event"
            try:
                event = await asyncio.wait_for(anext(stream), timeout=timeout)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"Timed out waiting for LLM stream {phase} after {timeout:.0f}s"
                ) from exc
            first_event = False
            event_kind = getattr(event, "event_kind", "")
            if event_kind == "function_tool_call":
                tool_calls_in_flight += 1
                tool_wait_timeout = max(
                    tool_wait_timeout, _tool_timeout_from_event(event)
                )
            elif event_kind == "function_tool_result":
                tool_calls_in_flight = max(0, tool_calls_in_flight - 1)
                if tool_calls_in_flight == 0:
                    tool_wait_timeout = 0.0
            yield event
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:
                pass


def _bash_command_decision(tc: Any, deps: "AgentDeps") -> "bool | None":
    """Check a bash tool call against session command-level rules.

    Returns True (allow), False (deny), or None (no match → ask user).
    """
    try:
        from suzent.tools.shell.permissions.rule_engine import (
            normalize_rules,
            evaluate_rules,
        )
        from suzent.tools.shell.permissions import CommandDecision

        perm_policies = getattr(deps, "tool_permission_policies", {}) or {}
        bash_policy = (
            perm_policies.get("bash_execute") or perm_policies.get("BashTool") or {}
        )
        raw_rules = (
            bash_policy.get("command_rules", [])
            if isinstance(bash_policy, dict)
            else []
        )
        if not raw_rules:
            return None

        command_text = ""
        if isinstance(tc.args, dict):
            command_text = tc.args.get("content", "") or ""
        if not command_text:
            return None

        rules = normalize_rules(raw_rules)
        decision = evaluate_rules(command_text, rules)
        if decision == CommandDecision.ALLOW:
            return True
        if decision == CommandDecision.DENY:
            return False
    except Exception:
        pass
    return None


def _bash_baseline_decision(tc: Any, deps: "AgentDeps") -> "bool | None":
    """Mirror bash_tool.py's internal baseline policy check.

    Auto-approves commands that bash would run without raising ApprovalRequired,
    so that setting requires_approval=True on BashTool doesn't break the desktop
    experience for simple commands.

    Returns:
        True  → safe, auto-approve (no dialog)
        False → hard-deny (dangerous pattern or blocked path)
        None  → needs user decision (git, chaining, policy-ASK)
    """
    try:
        from suzent.tools.shell.permissions import (
            evaluate_command_policy,
            CommandDecision,
        )
        from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver

        if not isinstance(tc.args, dict):
            return True  # malformed args — let bash handle it

        language = (tc.args.get("language") or "command").strip().lower()
        if language != "command":
            return True  # python / nodejs: no baseline restriction

        command_text = tc.args.get("content", "") or ""
        if not command_text:
            return True

        resolver = get_or_create_path_resolver(deps)
        baseline_eval = evaluate_command_policy(
            command_text=command_text,
            resolver=resolver,
            mode_value="accept_edits",
            raw_rules=[],
            default_action="ask",
        )

        _HARD_DENY_PREFIXES = (
            "Command blocked by high-risk shell semantics",
            "Path denied by policy",
            "Dangerous delete target blocked",
        )
        if (
            baseline_eval.decision == CommandDecision.DENY
            and baseline_eval.reason.startswith(_HARD_DENY_PREFIXES)
        ):
            return False

        _ASK_PREFIXES = (
            "Command requires approval due to shell chaining semantics",
            "Git commands require approval",
        )
        if (
            baseline_eval.decision == CommandDecision.ASK
            and baseline_eval.reason.startswith(_ASK_PREFIXES)
        ):
            return None  # show user dialog

        return True  # everything else is safe
    except Exception:
        return None  # on error, fall through to user dialog


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


def _find_tool_return_parts(
    msg: Any,
    current_deferred: Optional[DeferredToolResults],
    seen_tool_call_ids: Optional[set[str]] = None,
) -> list[tuple[str, str, str, str]]:
    """
    Extract tool return parts from a message for HITL recovery events.

    In pydantic-ai, ToolReturnPart is found inside ModelRequest messages
    (not ModelResponse, which only holds model-generated text/tool-calls).

    Returns list of tuples: (tool_call_id, tool_name, approval_status, output)
    """
    if not current_deferred or not hasattr(msg, "parts"):
        return []
    if msg.__class__.__name__ != "ModelRequest":
        return []

    results = []
    for part in msg.parts:
        if part.__class__.__name__ == "ToolReturnPart":
            tool_call_id = getattr(part, "tool_call_id", None)
            if tool_call_id and tool_call_id in current_deferred.approvals:
                if (
                    seen_tool_call_ids is not None
                    and tool_call_id in seen_tool_call_ids
                ):
                    continue
                tool_name = getattr(part, "tool_name", "unknown")
                status = (
                    "executed" if current_deferred.approvals[tool_call_id] else "denied"
                )
                output = (
                    getattr(part, "output", None)
                    or getattr(part, "content", None)
                    or getattr(part, "text", None)
                    or ""
                )
                output = _serialize_tool_output(output)
                logger.debug(
                    f"[Streaming] Found tool return part: {tool_call_id} -> {tool_name}, "
                    f"output_len={len(output)}"
                )
                results.append((tool_call_id, tool_name, status, output))
                if seen_tool_call_ids is not None:
                    seen_tool_call_ids.add(tool_call_id)
    return results


async def _queue_custom_event(
    out_queue: asyncio.Queue,
    event_name: str,
    data: Any,
) -> None:
    """Encode and queue a custom AG-UI event."""
    await out_queue.put(("chunk", _encode_custom(event_name, data)))


async def stream_agent_responses(
    agent: Agent,
    message: str | list | None,
    deps: AgentDeps,
    message_history: list | None = None,
    chat_id: Optional[str] = None,
    deferred_tool_results: Optional[DeferredToolResults] = None,
    is_heartbeat: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Runs the pydantic-ai agent with streaming and yields AG-UI formatted events.

    Uses a queue-based architecture: the agent runs in a background task so
    the generator can yield both regular events and HITL approval requests.
    HITL is handled seamlessly via deferred tools – if approvals are needed,
    the generator gracefully ends the stream, saving the agent state.
    """
    control = StreamControl()
    if chat_id:
        stream_controls[chat_id] = control
    # Indicates whether the stream paused waiting for user approvals.
    # When True, keep cached auto-approvals for the next resume request.
    deps.is_suspended = False

    sse_queue: asyncio.Queue = asyncio.Queue()
    deps.cancel_event = control.cancel_event

    # Auto-title: kick off in parallel for the first turn using only the user message
    # Extract text content for title generation
    _title_text: str | None = None
    if message and isinstance(message, str):
        _title_text = message.strip() or None
    elif message and isinstance(message, list):
        for _part in message:
            if isinstance(_part, dict) and _part.get("type") == "text":
                _title_text = (_part.get("text") or "").strip() or None
                break
            elif isinstance(_part, str):
                _title_text = _part.strip() or None
                break
    elif not _title_text and message_history:
        # message=None means the user text is already in message_history
        try:
            from pydantic_ai.messages import ModelRequest, UserPromptPart

            for _msg in reversed(message_history):
                if isinstance(_msg, ModelRequest):
                    for _part in _msg.parts:
                        if isinstance(_part, UserPromptPart) and isinstance(
                            _part.content, str
                        ):
                            _title_text = _part.content.strip() or None
                            break
                    if _title_text:
                        break
        except Exception:
            pass

    title_task = None
    if chat_id and not is_heartbeat and _title_text:
        try:
            from suzent.database import get_database as _get_db

            _chat = _get_db().get_chat(chat_id)
            _turn_count = getattr(_chat, "turn_count", 0) or 0
            logger.info(f"[AutoTitle] chat={chat_id} turn_count={_turn_count}")
            if _should_generate_auto_title(_chat):
                from suzent.core.auto_title import generate_auto_title

                _agent_model = getattr(agent, "_model_id", None) or getattr(
                    agent, "model", None
                )
                logger.info(f"[AutoTitle] creating task, model={_agent_model}")
                title_task = asyncio.create_task(
                    generate_auto_title(
                        chat_id, _title_text, fallback_model=_agent_model
                    )
                )
        except Exception as e:
            logger.warning(f"[AutoTitle] setup failed: {e}")

    # History tracker for cancellation recovery
    partial_history = list(message_history) if message_history else []

    out_queue: asyncio.Queue = asyncio.Queue()
    if chat_id:
        register_active_stream(chat_id, out_queue)

    # --- Background agent runner (stateless resume) ---
    async def _agent_runner() -> None:
        """Run the agent in a background task.

        Loops automatically when all pending tool approvals are satisfied by the
        session-level ``tool_approval_policy`` (always_allow / always_deny), so
        the user is never prompted for a tool they already approved this session.
        Terminates gracefully when human input is genuinely required or the agent
        finishes normally.
        """
        nonlocal partial_history
        final_response_text = ""
        original_count = len(message_history) if message_history else 0
        prompt = message
        history = list(message_history) if message_history else None
        current_deferred = deferred_tool_results

        try:
            logger.debug("[Streaming] Entering agent context (MCP init)...")
            async with agent:  # MCP server context management
                logger.debug("[Streaming] Agent context ready. Starting run loop.")
                while not control.cancel_event.is_set():
                    run_kwargs: Dict[str, Any] = {"deps": deps}
                    if history:
                        run_kwargs["message_history"] = history
                    if current_deferred:
                        run_kwargs["deferred_tool_results"] = current_deferred

                    last_run_result = None
                    logger.debug("[Streaming] Calling agent.run_stream_events()...")
                    async for event in _iter_stream_events_with_timeout(
                        agent, prompt, run_kwargs
                    ):
                        if control.cancel_event.is_set():
                            break
                        try:
                            logger.debug(
                                f"[Streaming] Received event from agent: {type(event).__name__}"
                            )
                            if isinstance(event, AgentRunResultEvent):
                                last_run_result = event.result
                                final_response_text = str(event.result.output)

                                # HITL BUG FIX: Emit deferred tool recovery events with output
                                if current_deferred:
                                    seen_recovery_ids: set[str] = set()
                                    for msg in event.result.all_messages():
                                        for (
                                            tool_call_id,
                                            tool_name,
                                            status,
                                            output,
                                        ) in _find_tool_return_parts(
                                            msg,
                                            current_deferred,
                                            seen_tool_call_ids=seen_recovery_ids,
                                        ):
                                            logger.debug(
                                                f"[Streaming] Emitting recovered tool event for {tool_call_id}"
                                            )
                                            await sse_queue.put(
                                                (
                                                    "tool_recovery",
                                                    {
                                                        "tool_call_id": tool_call_id,
                                                        "tool_name": tool_name,
                                                        "status": status,
                                                        "output": output,
                                                    },
                                                )
                                            )

                            await sse_queue.put(("event", event))
                        except Exception as e:
                            logger.error(
                                f"[Streaming] Error processing event {type(event).__name__}: {e}\n"
                                f"{traceback.format_exc()}"
                            )
                            # Emit error event to client instead of crashing stream
                            await sse_queue.put(
                                (
                                    "error",
                                    f"Error processing {type(event).__name__}: {str(e)}",
                                )
                            )
                            # Continue processing other events
                            continue

                    # Check if deferred tools need approval before terminating
                    if last_run_result and isinstance(
                        last_run_result.output, DeferredToolRequests
                    ):
                        current_history = last_run_result.all_messages()
                        partial_history = current_history
                        deps.last_messages = current_history

                        deferred = last_run_result.output
                        if deferred.approvals:
                            # Short-circuit: if auto_approve_tools is set (e.g. heartbeat / scheduler),
                            # approve all tools immediately without prompting the user.
                            if getattr(deps, "auto_approve_tools", False):
                                auto_approvals: Dict[str, bool] = {
                                    tc.tool_call_id: True for tc in deferred.approvals
                                }
                                current_deferred = DeferredToolResults(
                                    approvals=auto_approvals
                                )
                                history = current_history
                                prompt = ""
                                continue

                            # Split approvals into policy-decided (auto) and those
                            # still requiring the user's explicit decision.
                            auto_approvals: Dict[str, bool] = {}
                            pending_approvals = []
                            for tc in deferred.approvals:
                                policy = deps.tool_approval_policy.get(tc.tool_name, "")
                                if policy == "always_allow":
                                    auto_approvals[tc.tool_call_id] = True
                                    logger.debug(
                                        f"[Streaming] Auto-approving '{tc.tool_name}' "
                                        f"(always_allow policy)"
                                    )
                                elif policy == "always_deny":
                                    auto_approvals[tc.tool_call_id] = False
                                    logger.debug(
                                        f"[Streaming] Auto-denying '{tc.tool_name}' "
                                        f"(always_deny policy)"
                                    )
                                else:
                                    # For bash: check rules then baseline before asking user.
                                    # This preserves the original requires_approval=False
                                    # behaviour (only git/chained/dangerous require a dialog)
                                    # now that BashTool.requires_approval=True.
                                    if tc.tool_name in ("bash_execute", "BashTool"):
                                        # 1. Session/global command rules (remembered decisions)
                                        cmd_decision = _bash_command_decision(tc, deps)
                                        if cmd_decision is True:
                                            auto_approvals[tc.tool_call_id] = True
                                            logger.debug(
                                                "[Streaming] Auto-approving bash "
                                                "(command rule match)"
                                            )
                                            continue
                                        if cmd_decision is False:
                                            auto_approvals[tc.tool_call_id] = False
                                            logger.debug(
                                                "[Streaming] Auto-denying bash "
                                                "(command rule match)"
                                            )
                                            continue
                                        # 2. Baseline safety check (mirrors bash_tool.py logic)
                                        baseline = _bash_baseline_decision(tc, deps)
                                        if baseline is True:
                                            auto_approvals[tc.tool_call_id] = True
                                            logger.debug(
                                                "[Streaming] Auto-approving bash "
                                                "(baseline: safe command)"
                                            )
                                            continue
                                        if baseline is False:
                                            auto_approvals[tc.tool_call_id] = False
                                            logger.debug(
                                                "[Streaming] Auto-denying bash "
                                                "(baseline: dangerous command)"
                                            )
                                            continue
                                        # baseline is None → show approval dialog
                                    pending_approvals.append(tc)

                            if not pending_approvals:
                                # All tool approvals decided by policy — loop back
                                # immediately without pausing for user input.
                                current_deferred = DeferredToolResults(
                                    approvals=auto_approvals
                                )
                                history = current_history
                                prompt = ""  # no new user message on resume
                                continue  # restart loop

                            # Some tools still need the user's decision.
                            # Persist policy-decided approvals so resume can merge
                            # explicit user choices with these auto decisions.
                            if chat_id and auto_approvals:
                                merge_pending_auto_approvals(chat_id, auto_approvals)
                            deps.is_suspended = True  # Signal stream is pausing
                            for tc in pending_approvals:
                                try:
                                    args_dict = (
                                        tc.args if isinstance(tc.args, dict) else {}
                                    )
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

                    # Agent finished (or was cancelled) — exit loop
                    break

            # If this was a heartbeat run and it ended with HEARTBEAT_OK, rollback
            if not control.cancel_event.is_set() and is_heartbeat and chat_id:
                from suzent.core.heartbeat import get_active_heartbeat

                runner = get_active_heartbeat()
                if runner and runner._is_heartbeat_ok(final_response_text):
                    logger.info(f"Heartbeat HEARTBEAT_OK for {chat_id}, rolling back.")
                    partial_history = partial_history[:original_count]
                    deps.last_messages = partial_history
                    # Signal the frontend to discard the streamed heartbeat content.
                    await sse_queue.put(("heartbeat_ok", None))

        except Exception as e:
            logger.error(f"[Streaming] LLM call failed: {type(e).__name__}: {e}")
            await sse_queue.put(("error", e))
        finally:
            await sse_queue.put(("done", None))

    agent_task = asyncio.create_task(_agent_runner())

    # --- Native stream generator that feeds AGUIEventStream ---
    async def native_stream_generator() -> AsyncGenerator[Any, None]:
        async def _drain_a2ui_events() -> None:
            a2ui_queue = getattr(deps, "a2ui_queue", None)
            while a2ui_queue and not a2ui_queue.empty():
                try:
                    ev = a2ui_queue.get_nowait()
                    if (
                        ev.get("event") == "a2ui.render"
                        and ev.get("target") == "inline"
                        and ev.get("id")
                    ):
                        try:
                            deps.inline_a2ui_surfaces[ev["id"]] = dict(ev)
                        except Exception:
                            logger.debug(
                                "[Streaming] Failed to cache inline A2UI surface"
                            )
                    await out_queue.put(
                        (
                            "chunk",
                            _encode_custom(
                                ev["event"],
                                {
                                    "id": ev["id"],
                                    "title": ev.get("title", ""),
                                    "component": ev["component"],
                                    "target": ev.get("target", "canvas"),
                                    "deferred": ev.get("deferred", False),
                                    "chatId": chat_id,
                                },
                            ),
                        )
                    )
                except asyncio.QueueEmpty:
                    break

        while True:
            # Drain canvas/a2ui updates before waiting for stream events.
            await _drain_a2ui_events()

            try:
                msg = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
                msg_type, payload = msg

                if msg_type == "event":
                    if isinstance(payload, AgentRunResultEvent):
                        # Save message history — must not be gated on usage extraction
                        result_messages = None
                        try:
                            result_messages = payload.result.all_messages()
                            agent._last_messages = result_messages  # type: ignore[attr-defined]
                            deps.last_messages = result_messages
                        except Exception as e:
                            logger.warning(
                                f"[Streaming] Failed to extract message history: {e}"
                            )

                        # Extract usage data (independent — failure doesn't affect history)
                        try:
                            usage = payload.result.usage()
                            context_tokens = None
                            if result_messages is not None:
                                try:
                                    from suzent.config import CONFIG
                                    from suzent.core.context_compressor import (
                                        estimate_tokens,
                                    )

                                    context_tokens = estimate_tokens(
                                        result_messages,
                                        CONFIG.max_context_tokens,
                                    ).estimated_tokens
                                except Exception as e:
                                    logger.debug(
                                        f"[Streaming] Failed to estimate context usage: {e}"
                                    )

                            usage_data = {
                                "input_tokens": usage.input_tokens,
                                "output_tokens": usage.output_tokens,
                                "total_tokens": usage.total_tokens,
                                "context_tokens": context_tokens,
                                "cache_write_tokens": usage.cache_write_tokens,
                                "cache_read_tokens": usage.cache_read_tokens,
                                "requests": usage.requests,
                                "details": usage.details,
                            }
                            await out_queue.put(
                                ("chunk", _encode_custom("usage_update", usage_data))
                            )
                            if chat_id:
                                try:
                                    from suzent.database import get_database

                                    await asyncio.to_thread(
                                        get_database().update_chat,
                                        chat_id,
                                        context_usage=usage_data,
                                    )
                                except Exception as e:
                                    logger.debug(
                                        f"[Streaming] Failed to persist context usage: {e}"
                                    )
                            # Persist usage to the cost ledger
                            if usage.input_tokens or usage.output_tokens:
                                from suzent.core.cost_tracker import get_cost_tracker

                                _model_id = getattr(
                                    agent, "_model_id", None
                                ) or getattr(agent, "model", None)
                                await get_cost_tracker().log_cost(
                                    chat_id=chat_id,
                                    model=str(_model_id or "unknown"),
                                    role="primary",
                                    input_tokens=usage.input_tokens or 0,
                                    output_tokens=usage.output_tokens or 0,
                                    cache_write_tokens=usage.cache_write_tokens or 0,
                                    cache_read_tokens=usage.cache_read_tokens or 0,
                                )
                        except Exception as e:
                            logger.warning(
                                f"[Streaming] Failed to extract usage data: {e}"
                            )

                    try:
                        yield payload
                    except Exception as e:
                        logger.error(
                            f"[Streaming] Error yielding event: {e}\n"
                            f"{traceback.format_exc()}"
                        )
                        # Continue to next event instead of crashing

                elif msg_type == "approval":
                    # HITL: emit as AG-UI CustomEvent with all approval info
                    approval_info = {
                        "approvalId": payload["request_id"],
                        "toolCallId": payload.get("tool_call_id")
                        or payload["request_id"],
                        "toolName": payload.get("tool_name", ""),
                        "args": payload.get("args", {}),
                        "chatId": chat_id,
                    }
                    await _queue_custom_event(
                        out_queue,
                        "tool_approval_request",
                        approval_info,
                    )
                    # Persist pending approval to DB so the frontend can
                    # reconstruct the approval dialog after a page refresh.
                    if chat_id:
                        try:
                            from suzent.database import get_database as _get_db

                            def _save_pending_approval():
                                _db = _get_db()
                                _chat = _db.get_chat(chat_id)
                                if _chat is not None:
                                    _cfg = dict(_chat.config or {})
                                    # Accumulate multiple pending approvals
                                    existing = _cfg.get("_pending_approvals") or []
                                    if isinstance(existing, list):
                                        existing = [
                                            a for a in existing
                                            if a.get("toolCallId") != approval_info["toolCallId"]
                                        ]
                                    else:
                                        existing = []
                                    existing.append({
                                        "approvalId": approval_info["approvalId"],
                                        "toolCallId": approval_info["toolCallId"],
                                        "toolName": approval_info["toolName"],
                                        "args": approval_info["args"],
                                        "savedAt": __import__("datetime").datetime.utcnow().isoformat(),
                                    })
                                    _cfg["_pending_approvals"] = existing
                                    _db.update_chat(chat_id, config=_cfg)

                            await asyncio.to_thread(_save_pending_approval)
                        except Exception as _pa_err:
                            logger.debug(f"[Streaming] Failed to save pending_approval: {_pa_err}")

                elif msg_type == "tool_recovery":
                    # HITL: emit recovered tool result with output
                    await _queue_custom_event(
                        out_queue,
                        "tool_approval_result",
                        {
                            "toolCallId": payload["tool_call_id"],
                            "toolName": payload.get("tool_name", ""),
                            "status": payload.get("status", "executed"),
                            "output": payload.get("output", ""),
                        },
                    )

                elif msg_type == "heartbeat_ok":
                    # Tell the frontend to discard streamed heartbeat content.
                    await _queue_custom_event(out_queue, "heartbeat_ok", {})

                elif msg_type == "done":
                    # Final flush to avoid dropping last-moment canvas/a2ui updates.
                    await _drain_a2ui_events()
                    break

                elif msg_type == "error":
                    err = RunErrorEvent(message=str(payload))
                    await out_queue.put(("chunk", _encoder.encode(err)))
                    break

            except asyncio.TimeoutError:
                if control.cancel_event.is_set():
                    break

    # --- Background worker to encode stream using AGUIEventStream ---
    async def encode_worker() -> None:
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

        # Signal frontend to refresh goal/task sidebar.
        if not control.cancel_event.is_set() and chat_id:
            yield _encode_custom("plan_refresh", {})

        # Deliver auto-title (runs in parallel, should already be done by now)
        if title_task is not None and not control.cancel_event.is_set():
            try:
                title = await title_task
                if title:
                    yield _encode_custom(
                        "chat_title_updated", {"chat_id": chat_id, "title": title}
                    )
            except Exception:
                pass

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

        # Ensure memory is saved even on early termination (cancellation, tool error, etc.)
        if getattr(deps, "last_messages", None) is None:
            try:
                agent._last_messages = partial_history
                deps.last_messages = partial_history
            except Exception as e:
                logger.error(f"Failed to reconstruct partial history: {e}")

        if chat_id:
            if not getattr(deps, "is_suspended", False):
                # Stream ended (not paused for approvals), drop any stale cache.
                pop_pending_auto_approvals(chat_id)
                # Clear persisted pending approvals so the frontend doesn't
                # show a stale dialog on next load.
                try:
                    from suzent.database import get_database as _get_db2

                    async def _clear_pending_approvals_task():
                        try:
                            def _sync_clear():
                                _db2 = _get_db2()
                                _chat2 = _db2.get_chat(chat_id)
                                if _chat2 is not None:
                                    _cfg2 = dict(_chat2.config or {})
                                    if "_pending_approvals" in _cfg2:
                                        del _cfg2["_pending_approvals"]
                                        _db2.update_chat(chat_id, config=_cfg2)
                            await asyncio.to_thread(_sync_clear)
                        except Exception:
                            pass

                    asyncio.create_task(_clear_pending_approvals_task())
                except Exception as _cp_err:
                    logger.debug(f"[Streaming] Failed to clear pending_approvals: {_cp_err}")

            existing = stream_controls.get(chat_id)
            if existing is control:
                stream_controls.pop(chat_id, None)
            unregister_active_stream(chat_id)

        # Signal that all cleanup (including post-processing trigger) is done
        control.completed_event.set()
