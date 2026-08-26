"""
Stream event type constants for AG-UI protocol.

Defines standard event names used across the codebase to prevent typos
and enable easier refactoring. These match the AG-UI protocol specification.

See: https://github.com/pydantic/pydantic-ai/tree/main/packages/ag-ui
"""

from enum import Enum


class StreamEventType(str, Enum):
    """
    Standard AG-UI stream event types.

    These are emitted by pydantic-ai and consumed by the frontend.
    Using an Enum ensures type safety and prevents typos.
    """

    # Text message events
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"

    # Thinking/reasoning events
    THINKING_START = "THINKING_START"
    THINKING_TEXT_MESSAGE_START = "THINKING_TEXT_MESSAGE_START"
    THINKING_TEXT_MESSAGE_CONTENT = "THINKING_TEXT_MESSAGE_CONTENT"
    THINKING_TEXT_MESSAGE_END = "THINKING_TEXT_MESSAGE_END"
    THINKING_END = "THINKING_END"
    # ag-ui-protocol 0.1.13 renamed the thinking family to REASONING_*.
    # pydantic-ai emits whichever family the negotiated protocol version calls
    # for, so both names are live and both must be recognised.
    REASONING_START = "REASONING_START"
    REASONING_MESSAGE_START = "REASONING_MESSAGE_START"
    REASONING_MESSAGE_CONTENT = "REASONING_MESSAGE_CONTENT"
    REASONING_MESSAGE_CHUNK = "REASONING_MESSAGE_CHUNK"
    REASONING_MESSAGE_END = "REASONING_MESSAGE_END"
    REASONING_END = "REASONING_END"
    REASONING_ENCRYPTED_VALUE = "REASONING_ENCRYPTED_VALUE"

    # Tool call events
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"

    # Custom events
    CUSTOM = "CUSTOM"
    CUSTOM_EVENT = "CUSTOM_EVENT"

    # Error and completion events
    RUN_ERROR = "RUN_ERROR"
    RUN_STARTED = "RUN_STARTED"
    AGENT_FINISHED = "AGENT_FINISHED"

    # Legacy smolagents events (deprecated but supported for migration)
    STREAM_DELTA = "stream_delta"
    TOOL_OUTPUT = "tool_output"
    ERROR = "error"
    FINAL_ANSWER = "final_answer"


class CustomEventName(str, Enum):
    """
    Custom event names used by Suzent.

    These are emitted as CUSTOM events with a name field.
    """

    # Tool approval (HITL)
    TOOL_APPROVAL_REQUEST = "tool_approval_request"

    # Rich tool display
    TOOL_DISPLAY = "tool_display"

    # Plan updates
    PLAN_REFRESH = "plan_refresh"

    # Usage tracking
    USAGE_UPDATE = "usage_update"

    # A2UI canvas rendering
    A2UI_RENDER = "a2ui.render"

    # Agent-activated tool notification
    TOOL_ACTIVATED = "tool_activated"

    # Raw Agent Client Protocol session update
    ACP_SESSION_UPDATE = "acp.session_update"

    # ACP agent is asking the user (or a Suzent agent) to approve a tool call
    ACP_PERMISSION_REQUEST = "acp.permission_request"

    # A resume fell back to a fresh ACP session, so prior history is gone
    ACP_SESSION_RESET = "acp.session_reset"


# Backwards compatibility aliases
TEXT_MESSAGE_CONTENT = StreamEventType.TEXT_MESSAGE_CONTENT
TOOL_CALL = StreamEventType.TOOL_CALL_START
TOOL_RETURN = StreamEventType.TOOL_CALL_RESULT
CUSTOM = StreamEventType.CUSTOM


def is_text_event(event_type: str) -> bool:
    """Check if an event type is a text message event."""
    return event_type in {
        StreamEventType.TEXT_MESSAGE_START,
        StreamEventType.TEXT_MESSAGE_CONTENT,
        StreamEventType.TEXT_MESSAGE_END,
    }


def is_thinking_event(event_type: str) -> bool:
    """Check if an event type is a thinking/reasoning event."""
    return event_type in {
        StreamEventType.THINKING_START,
        StreamEventType.THINKING_TEXT_MESSAGE_START,
        StreamEventType.THINKING_TEXT_MESSAGE_CONTENT,
        StreamEventType.THINKING_TEXT_MESSAGE_END,
        StreamEventType.THINKING_END,
        StreamEventType.REASONING_START,
        StreamEventType.REASONING_MESSAGE_START,
        StreamEventType.REASONING_MESSAGE_CONTENT,
        StreamEventType.REASONING_MESSAGE_CHUNK,
        StreamEventType.REASONING_MESSAGE_END,
        StreamEventType.REASONING_END,
        StreamEventType.REASONING_ENCRYPTED_VALUE,
    }


def is_tool_event(event_type: str) -> bool:
    """Check if an event type is a tool call event."""
    return event_type in {
        StreamEventType.TOOL_CALL_START,
        StreamEventType.TOOL_CALL_ARGS,
        StreamEventType.TOOL_CALL_END,
        StreamEventType.TOOL_CALL_RESULT,
    }


def is_legacy_event(event_type: str) -> bool:
    """Check if an event type is a legacy smolagents event."""
    return event_type in {
        StreamEventType.STREAM_DELTA,
        StreamEventType.TOOL_OUTPUT,
        StreamEventType.ERROR,
        StreamEventType.FINAL_ANSWER,
    }
