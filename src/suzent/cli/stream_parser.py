"""
Stream Parser for CLI.

Handles parsing of Server-Sent Events (SSE) from the Suzent chat API,
providing a robust state machine for handling CodeAgent outputs, tool calls,
and error states.
"""

import json
from dataclasses import dataclass
from typing import Iterator, Optional, Union


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

    def __init__(self, code_tag: str = "<code>"):
        self.code_tag = code_tag
        self.buffer = ""
        self.is_in_code_block = False
        self.pending_code_probe = ""
        self.detected_agent_type: Optional[str] = None

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
            tool_name = data.get("tool_call", {}).get("name", "unknown")
            output = data.get("output", "") or data.get("observation", "")
            yield ToolOutput(tool_name, str(output))

        elif evt_type == "action":
            # Handle observations/logs if present
            if data.get("observations"):
                # Clean up CodeAgent specific log headers if needed
                obs = data["observations"]
                # Heuristic cleanup similar to frontend
                obs = obs.replace("Execution logs:\n", "").strip()
                yield ToolOutput("system", obs)

        elif evt_type == "error":
            yield ErrorEvent(str(data))

        elif evt_type == "final_answer":
            # Flush any pending buffer
            if self.pending_code_probe:
                yield TextChunk(self.pending_code_probe, self.is_in_code_block)
                self.pending_code_probe = ""

            yield FinalAnswer(str(data))

    def _handle_delta(self, data: dict) -> Iterator[StreamEvent]:
        """Handle stream_delta content, filtering code tags."""
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

        # Code tag filtering (simple state machine)
        # Scan content for code_tag
        content = self.pending_code_probe + content
        self.pending_code_probe = ""

        pos = 0
        while True:
            idx = content.find(self.code_tag, pos)
            if idx == -1:
                break

            # Yield content up to tag
            text_segment = content[pos:idx]
            if text_segment:
                yield TextChunk(text_segment, self.is_in_code_block)

            # Toggle state
            self.is_in_code_block = not self.is_in_code_block

            # Start strict code block or end it
            # In CLI, we might want to just print it as is, or colorize it.
            # For now, we yield it as TextChunk with is_code=True for potential styling.

            pos = idx + len(self.code_tag)

        # Handle remaining content
        leftover = content[pos:]

        # Check for partial tag at end
        # Only relevant if tag is multi-char and we split in middle of it.
        # code_tag is usually "<code>".
        # We need to buffer if end matches partial tag.
        keep_len = 0
        for k in range(1, len(self.code_tag)):
            if len(leftover) >= k and self.code_tag.startswith(leftover[-k:]):
                keep_len = k
                break

        if keep_len > 0:
            self.pending_code_probe = leftover[-keep_len:]
            to_yield = leftover[:-keep_len]
            if to_yield:
                yield TextChunk(to_yield, self.is_in_code_block)
        else:
            if leftover:
                yield TextChunk(leftover, self.is_in_code_block)
