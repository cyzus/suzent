"""
Stream Parser for CLI.

Handles parsing of Server-Sent Events (SSE) from the Suzent chat API,
providing a robust state machine for handling CodeAgent outputs, tool calls,
and error states.
"""

import json
from dataclasses import dataclass
from typing import Iterator, Union


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


class StreamParser:
    """
    Stateful parser for Suzent agent streams.

    Handles:
    - SSE format parsing (data: ...)
    - CodeAgent <code> tag filtering
    - Tool call/output formatting
    - Agent thought vs final answer differentiation
    """

    def __init__(self):
        self.buffer = ""

    def parse(self, lines: Iterator[Union[str, bytes]]) -> Iterator[StreamEvent]:
        """
        Parse an iterator of lines (bytes or strings) into StreamEvents.
        """
        for line in lines:
            line_str = (
                line
                if isinstance(line, str)
                else line.decode("utf-8", errors="replace")
            )

            if not line_str.startswith("data: "):
                continue

            json_str = line_str[6:].strip()
            if not json_str:
                continue

            try:
                data = json.loads(json_str)
                yield from self._handle_event(data)
            except json.JSONDecodeError:
                continue

    def _handle_event(self, payload: dict) -> Iterator[StreamEvent]:
        """Process a single JSON event payload."""
        evt_type = payload.get("type")
        data = payload.get("data")

        if evt_type == "stream_delta":
            yield from self._handle_delta(data)

        elif evt_type == "tool_call":
            # Some implementations send tool_call as distinct event
            # or it might be embedded in stream_delta.
            # Handle explicit event if present.
            pass

        elif evt_type == "tool_output":
            # Support both old format (tool_call.name) and new format (tool_name)
            tool_name = data.get("tool_name") or data.get("tool_call", {}).get(
                "name", "unknown"
            )
            output = data.get("output", "") or data.get("observation", "")
            yield ToolOutput(tool_name, str(output))

        elif evt_type == "action":
            # Handle tool call announcements from pydantic-ai
            if data.get("tool_calls"):
                for tc in data["tool_calls"]:
                    yield ToolCall(
                        tc.get("name", "unknown"),
                        tc.get("arguments", {}),
                    )
            # Handle observations/logs if present (legacy)
            elif data.get("observations"):
                obs = data["observations"]
                obs = obs.replace("Execution logs:\n", "").strip()
                yield ToolOutput("system", obs)

        elif evt_type == "error":
            yield ErrorEvent(str(data))

        elif evt_type == "final_answer":
            yield FinalAnswer(str(data))

    def _handle_delta(self, data: dict) -> Iterator[StreamEvent]:
        """Handle stream_delta content."""
        content = data.get("content", "")

        # ToolCallingAgent: handle tool_calls in delta
        if data.get("tool_calls"):
            for tc in data["tool_calls"]:
                name = tc.get("function", {}).get("name", "unknown")
                args = tc.get("function", {}).get("arguments", {})
                yield ToolCall(name, args)
            return

        if not content:
            return

        yield TextChunk(content, False)
