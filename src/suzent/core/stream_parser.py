"""
Stream Parser for Suzent.

Handles parsing of Server-Sent Events (SSE) from the Suzent chat API,
providing a robust state machine for handling CodeAgent outputs, tool calls,
and error states.
"""

import json
from dataclasses import dataclass
from typing import Iterator, Union

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


@dataclass
class ToolOutput(StreamEvent):
    """Output from a tool execution."""

    tool_name: str
    output: str


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
            return f"{text}Arguments: None"

        text += "Arguments:\n"
        for k, v in self.args.items():
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


class StreamParser:
    """
    Stateful parser for Suzent agent streams.

    Handles:
    - SSE format parsing (data: ...)
    - Modern Suzent events (TEXT_MESSAGE_CONTENT, TOOL_CALL, TOOL_RETURN, etc.)
    - Custom events like tool_approval_request
    - Legacy fallbacks for older agents
    """

    def __init__(self):
        self.buffer = ""

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
            yield ToolCall(
                payload.get("tool_name", "unknown"),
                payload.get("args", {}),
            )
        elif evt_type == StreamEventType.TOOL_CALL_RESULT:
            yield ToolOutput(
                payload.get("tool_name", "unknown"),
                str(payload.get("output", "")),
            )
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
                )
        elif evt_type == StreamEventType.RUN_ERROR:
            yield ErrorEvent(payload.get("message", "Unknown error"))
        elif evt_type == StreamEventType.AGENT_FINISHED:
            # Just a terminator
            pass

        # --- Legacy Fallbacks ---
        elif evt_type == StreamEventType.STREAM_DELTA:
            data = payload.get("data", {})
            yield from self._handle_delta(data)
        elif evt_type == StreamEventType.TOOL_OUTPUT:
            data = payload.get("data", {})
            tool_name = data.get("tool_name") or data.get("tool_call", {}).get(
                "name", "unknown"
            )
            yield ToolOutput(tool_name, str(data.get("output", "")))
        elif evt_type == StreamEventType.ERROR:
            data = payload.get("data", {})
            yield ErrorEvent(str(data))
        elif evt_type == StreamEventType.FINAL_ANSWER:
            data = payload.get("data", {})
            yield FinalAnswer(str(data))

    def _handle_delta(self, data: dict) -> Iterator[StreamEvent]:
        """Handle legacy stream_delta content."""
        content = data.get("content", "")
        if data.get("tool_calls"):
            for tc in data["tool_calls"]:
                name = tc.get("function", {}).get("name", "unknown")
                args = tc.get("function", {}).get("arguments", {})
                yield ToolCall(name, args)
            return

        if not content:
            return
        yield TextChunk(content, False)
