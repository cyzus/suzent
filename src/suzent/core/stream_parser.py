"""
Stream Parser for Suzent.

Handles parsing of Server-Sent Events (SSE) from the Suzent chat API,
providing a robust state machine for handling CodeAgent outputs, tool calls,
and error states.
"""

import json
from dataclasses import dataclass
from typing import Any, Iterator, Union

from suzent.core.stream_events import StreamEventType, CustomEventName
from suzent.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StreamEvent:
    """Base class for parsed stream events."""

    pass


@dataclass
class TextChunk(StreamEvent):
    """A chunk of text content to be displayed."""

    content: str
    is_code: bool = False


@dataclass
class ToolCall(StreamEvent):
    """Notification of a tool call."""

    tool_name: str
    arguments: dict
    tool_call_id: str = ""
    # Raw argument text as it came off the wire, kept so unparseable or
    # truncated JSON is still displayable.
    raw_arguments: str = ""

    def format_arguments(self, max_length: int = 200) -> str:
        """Compact one-line rendering of the arguments for terminal display."""
        if self.arguments:
            try:
                text = json.dumps(self.arguments, ensure_ascii=False)
            except (TypeError, ValueError):
                text = str(self.arguments)
        else:
            text = " ".join((self.raw_arguments or "").split())
        if len(text) > max_length:
            return text[: max_length - 1] + "\u2026"
        return text


@dataclass
class ToolOutput(StreamEvent):
    """Output from a tool execution."""

    tool_name: str
    output: str
    tool_call_id: str = ""


@dataclass
class _PendingToolCall:
    """A tool call being assembled from TOOL_CALL_START/ARGS/END events."""

    tool_name: str
    args_text: str = ""
    # Legacy emitters send the whole argument dict on the start event.
    inline_args: dict | None = None
    emitted: bool = False


@dataclass
class ErrorEvent(StreamEvent):
    """An error that occurred during generation."""

    message: str


@dataclass
class FinalAnswer(StreamEvent):
    """The final answer from the agent."""

    content: str


@dataclass
class ApprovalRequest(StreamEvent):
    """A tool call that requires human-in-the-loop approval."""

    request_id: str
    tool_call_id: str
    tool_name: str
    args: dict
    decision: dict[str, Any] | None = None

    def format_args(self) -> str:
        """Return a pretty JSON string of the arguments."""
        if not self.args:
            return "{}"
        return json.dumps(self.args, indent=2)

    def format_alert_text(self, markdown: bool = True) -> str:
        """Get a standardized, plain-text friendly alert message body."""
        tool_fmt = f"`{self.tool_name}`" if markdown else self.tool_name
        text = f"Tool: {tool_fmt}\n"

        if not self.args:
            return text.strip()

        text += "Arguments:\n"

        # Show high-level intent first so approval UIs are easier to scan.
        keys = list(self.args.keys())
        if "description" in self.args:
            keys = ["description"] + [k for k in keys if k != "description"]

        for k in keys:
            v = self.args.get(k)
            if isinstance(v, (dict, list)):
                # Fallback to JSON for complex structures
                val_str = json.dumps(v)
            else:
                val_str = str(v)

            if markdown:
                text += f"- **{k}**: {val_str}\n"
            else:
                text += f"- {k}: {val_str}\n"

        return text.strip()


_TOOL_CALL_ID_KEYS = ("toolCallId", "tool_call_id", "id")
_TOOL_NAME_KEYS = ("toolCallName", "toolName", "tool_name", "name")


def _first_str(payload: dict, keys: tuple[str, ...]) -> str:
    """Return the first non-empty string value found under ``keys``."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _stringify(raw: Any) -> str:
    """Render tool output content (string, list of parts, or dict) as text."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(raw)


def _parse_arguments(raw: str) -> dict:
    """Parse accumulated TOOL_CALL_ARGS text into a dict (empty if unusable)."""
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.debug(f"Unparseable tool call arguments: {text[:200]}")
        return {}
    return parsed if isinstance(parsed, dict) else {}


class StreamParser:
    """
    Stateful parser for Suzent agent streams.

    Handles:
    - SSE format parsing (data: ...)
    - Modern Suzent events (TEXT_MESSAGE_CONTENT, TOOL_CALL, TOOL_RETURN, etc.)
    - Custom events like tool_approval_request
    - Legacy fallbacks for older agents

    Tool calls arrive as TOOL_CALL_START (id + name), a run of TOOL_CALL_ARGS
    deltas, then TOOL_CALL_END. A single ToolCall is emitted once the call
    closes, so its arguments are complete when consumers see it.
    """

    def __init__(self):
        self.buffer = ""
        self._pending_tools: dict[str, _PendingToolCall] = {}
        self._last_tool_call_id = ""

    def parse(self, chunks: Iterator[Union[str, bytes]]) -> Iterator[StreamEvent]:
        """
        Parse an iterator of data chunks (bytes or strings) into StreamEvents.
        Handles multi-line chunks and chunks split across boundaries.
        """
        for chunk in chunks:
            chunk_str = (
                chunk
                if isinstance(chunk, str)
                else chunk.decode("utf-8", errors="replace")
            )
            self.buffer += chunk_str

            # SSE events are separated by double newlines
            while "\n\n" in self.buffer:
                event_block, self.buffer = self.buffer.split("\n\n", 1)
                logger.debug(f"Parsing SSE block: {event_block[:100]}...")

                # An event block can have multiple lines (data:, event:, id:, retry:)
                # We only care about the "data:" lines for now.
                for line in event_block.splitlines():
                    if line.startswith("data: "):
                        json_str = line[6:].strip()
                        if not json_str or json_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(json_str)
                            yield from self._handle_event(data)
                        except json.JSONDecodeError:
                            continue

    def _handle_event(self, payload: dict) -> Iterator[StreamEvent]:
        """Process a single JSON event payload."""
        evt_type = payload.get("type")

        # --- Modern Suzent Streaming Events ---
        if evt_type == StreamEventType.TEXT_MESSAGE_CONTENT:
            yield TextChunk(payload.get("delta", ""), False)
        elif evt_type == StreamEventType.TOOL_CALL_START:
            self._start_tool_call(payload)
        elif evt_type == StreamEventType.TOOL_CALL_ARGS:
            self._record_tool_call_args(payload)
        elif evt_type == StreamEventType.TOOL_CALL_END:
            yield from self._emit_tool_call(self._resolve_tool_call_id(payload))
        elif evt_type == StreamEventType.TOOL_CALL_RESULT:
            yield from self._handle_tool_call_result(payload)
        elif evt_type in (StreamEventType.CUSTOM_EVENT, StreamEventType.CUSTOM):
            # The AG-UI protocol uses type: CUSTOM with top-level name/value
            # but some internal emitters might use type: CUSTOM_EVENT with nested custom object.
            name = payload.get("name")
            value = payload.get("value")

            if not name and "custom" in payload:
                custom = payload.get("custom", {})
                name = custom.get("name")
                value = custom.get("value")

            if name == CustomEventName.TOOL_APPROVAL_REQUEST:
                val = value or {}
                yield ApprovalRequest(
                    request_id=val.get("approvalId", ""),
                    tool_call_id=val.get("toolCallId", ""),
                    tool_name=val.get("toolName", "unknown"),
                    args=val.get("args", {}),
                    decision=val.get("decision"),
                )
        elif evt_type == StreamEventType.RUN_ERROR:
            # A failed run may leave tool calls that never closed.
            yield from self.flush()
            yield ErrorEvent(payload.get("message", "Unknown error"))
        elif evt_type == StreamEventType.AGENT_FINISHED:
            yield from self.flush()

        # --- Legacy Fallbacks ---
        elif evt_type == StreamEventType.STREAM_DELTA:
            data = payload.get("data", {})
            yield from self._handle_delta(data)
        elif evt_type == StreamEventType.TOOL_OUTPUT:
            data = payload.get("data", {})
            tool_call = data.get("tool_call", {}) or {}
            tool_name = data.get("tool_name") or tool_call.get("name", "unknown")
            yield ToolOutput(
                tool_name,
                _stringify(data.get("output", "")),
                tool_call_id=str(data.get("tool_call_id") or tool_call.get("id") or ""),
            )
        elif evt_type == StreamEventType.ERROR:
            data = payload.get("data", {})
            yield ErrorEvent(str(data))
        elif evt_type == StreamEventType.FINAL_ANSWER:
            data = payload.get("data", {})
            yield FinalAnswer(str(data))

    # --- Tool call assembly -------------------------------------------------

    def flush(self) -> Iterator[StreamEvent]:
        """
        Emit any tool call that never saw a TOOL_CALL_END or a result.

        Consumers can call this once a stream is exhausted so a truncated run
        still reports the tools it started.
        """
        for call_id in list(self._pending_tools):
            yield from self._emit_tool_call(call_id)
            self._pending_tools.pop(call_id, None)

    def _resolve_tool_call_id(self, payload: dict) -> str:
        """Tool call id from the payload, falling back to the call in flight."""
        return _first_str(payload, _TOOL_CALL_ID_KEYS) or self._last_tool_call_id

    def _start_tool_call(self, payload: dict) -> None:
        """Register a tool call; its arguments stream in as TOOL_CALL_ARGS."""
        call_id = self._resolve_tool_call_id(payload)
        pending = _PendingToolCall(
            tool_name=_first_str(payload, _TOOL_NAME_KEYS) or "unknown"
        )

        raw_args = payload.get("args")
        if isinstance(raw_args, dict):
            pending.inline_args = raw_args
        elif isinstance(raw_args, str):
            pending.args_text = raw_args

        # A replayed start (resume after approval) restarts argument streaming.
        self._pending_tools[call_id] = pending
        self._last_tool_call_id = call_id

    def _record_tool_call_args(self, payload: dict) -> None:
        """Accumulate one TOOL_CALL_ARGS delta."""
        delta = payload.get("delta")
        if not isinstance(delta, str) or not delta:
            return

        call_id = self._resolve_tool_call_id(payload)
        pending = self._pending_tools.get(call_id)
        if pending is None:
            # Args without a start: still keep them so the call has arguments.
            pending = _PendingToolCall(tool_name="unknown")
            self._pending_tools[call_id] = pending
            self._last_tool_call_id = call_id
        pending.args_text += delta

    def _emit_tool_call(self, call_id: str) -> Iterator[StreamEvent]:
        """Emit the pending call for ``call_id`` exactly once."""
        pending = self._pending_tools.get(call_id)
        if pending is None or pending.emitted:
            return
        pending.emitted = True

        if pending.inline_args is not None:
            arguments = pending.inline_args
        else:
            arguments = _parse_arguments(pending.args_text)

        yield ToolCall(
            pending.tool_name,
            arguments,
            tool_call_id=call_id,
            raw_arguments=pending.args_text,
        )

    def _handle_tool_call_result(self, payload: dict) -> Iterator[StreamEvent]:
        """Emit the tool's output, closing the call first if it is still open."""
        call_id = self._resolve_tool_call_id(payload)
        # A result implies the call closed, even if TOOL_CALL_END never arrived.
        yield from self._emit_tool_call(call_id)
        pending = self._pending_tools.pop(call_id, None)

        content = payload.get("content")
        if content is None:
            content = payload.get("output")
        if content is None:
            content = payload.get("result")

        tool_name = (
            _first_str(payload, _TOOL_NAME_KEYS)
            or (pending.tool_name if pending else "")
            or "unknown"
        )
        yield ToolOutput(tool_name, _stringify(content), tool_call_id=call_id)

    def _handle_delta(self, data: dict) -> Iterator[StreamEvent]:
        """Handle legacy stream_delta content."""
        content = data.get("content", "")
        if data.get("tool_calls"):
            for tc in data["tool_calls"]:
                fn = tc.get("function", {}) or {}
                raw_args = fn.get("arguments", {})
                if isinstance(raw_args, str):
                    args, raw_text = _parse_arguments(raw_args), raw_args
                elif isinstance(raw_args, dict):
                    args, raw_text = raw_args, ""
                else:
                    args, raw_text = {}, ""
                yield ToolCall(
                    fn.get("name", "unknown"),
                    args,
                    tool_call_id=str(tc.get("id") or ""),
                    raw_arguments=raw_text,
                )
            return

        if not content:
            return
        yield TextChunk(content, False)
