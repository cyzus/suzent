import pytest
from unittest.mock import patch
from suzent.core.chat_processor import ChatProcessor
from suzent.core.stream_parser import (
    StreamParser,
    ApprovalRequest,
    TextChunk,
    ErrorEvent,
)


def test_stream_parser_approval_request():
    """Verify that StreamParser correctly parses tool_approval_request events with the actual wire protocol."""
    parser = StreamParser()
    # The actual wire protocol seen in logs: {"type":"CUSTOM","name":"tool_approval_request","value":{...}}
    chunk = (
        'data: {"type": "CUSTOM", "name": "tool_approval_request", '
        '"value": {"approvalId": "req123", "toolName": "search", "args": {"q": "test"}}}'
        "\n\n"
    )
    events = list(parser.parse([chunk]))

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ApprovalRequest)
    assert event.request_id == "req123"
    assert event.tool_name == "search"
    assert event.args == {"q": "test"}


def test_approval_request_formatting():
    """Verify the new plain-text friendly formatting."""
    event = ApprovalRequest(
        request_id="req123",
        tool_call_id="call_abc",
        tool_name="search",
        args={"q": "suzent", "limit": 5},
    )

    # Test Markdown version
    md_text = event.format_alert_text(markdown=True)
    assert "Tool: `search`" in md_text
    assert "- **q**: suzent" in md_text
    assert "- **limit**: 5" in md_text

    # Test Plain Text version
    pt_text = event.format_alert_text(markdown=False)
    assert "Tool: search" in pt_text
    assert "- q: suzent" in pt_text
    assert "- limit: 5" in pt_text


def test_approval_request_formats_description_first():
    event = ApprovalRequest(
        request_id="req123",
        tool_call_id="call_abc",
        tool_name="bash_execute",
        args={
            "content": "ls -la",
            "description": "List files in current working directory",
            "language": "command",
        },
    )

    text = event.format_alert_text(markdown=False)
    desc_index = text.find("- description: List files in current working directory")
    content_index = text.find("- content: ls -la")

    assert desc_index != -1
    assert content_index != -1
    assert desc_index < content_index


def test_stream_parser_fragmented_and_multi():
    """Verify that StreamParser handles fragmented and multi-event chunks."""
    parser = StreamParser()

    # Chunk 1: Partial event
    events1 = list(parser.parse(['data: {"type": "TEXT_MESSAGE_CONT']))
    assert len(events1) == 0

    # Chunk 2: Completes event 1 AND starts event 2
    events2 = list(
        parser.parse(['ENT", "delta": "Hello"}\n\ndata: {"type": "TEXT_MESSAG'])
    )
    assert len(events2) == 1
    assert isinstance(events2[0], TextChunk)
    assert events2[0].content == "Hello"

    # Chunk 3: Completes event 2 and adds event 3
    events3 = list(
        parser.parse(
            [
                'E_CONTENT", "delta": " World"}\n\ndata: {"type": "RUN_ERROR", "message": "fail"}\n\n'
            ]
        )
    )
    assert len(events3) == 2
    assert isinstance(events3[0], TextChunk)
    assert events3[0].content == " World"
    assert isinstance(events3[1], ErrorEvent)
    assert events3[1].message == "fail"


@pytest.mark.asyncio
async def test_chat_processor_on_event_callback():
    """Verify that ChatProcessor.process_turn_text triggers the on_event callback."""
    processor = ChatProcessor()

    # Mock process_turn to return chunks
    async def mock_gen(*args, **kwargs):
        yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "Hello"}\n\n'
        yield (
            'data: {"type": "CUSTOM_EVENT", "custom": {"name": "tool_approval_request", '
            '"value": {"approvalId": "req456", "toolName": "calc", "args": {"x": 1}}}}\n\n'
        )
        yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": " world"}\n\n'

    with patch.object(processor, "process_turn", side_effect=mock_gen):
        events_received = []

        async def on_event(event):
            events_received.append(event)

        full_response = await processor.process_turn_text(
            chat_id="test_chat",
            user_id="user1",
            message_content="hi",
            on_event=on_event,
        )

        assert full_response == "Hello world"
        assert len(events_received) == 3
        assert isinstance(events_received[0], TextChunk)
        assert isinstance(events_received[1], ApprovalRequest)
        assert events_received[1].request_id == "req456"
        assert isinstance(events_received[2], TextChunk)
