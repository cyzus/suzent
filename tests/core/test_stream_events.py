import pytest
from unittest.mock import patch
from suzent.core.chat_processor import ChatProcessor
from suzent.core.stream_parser import (
    StreamParser,
    ApprovalRequest,
    TextChunk,
    ErrorEvent,
    ToolCall,
    ToolOutput,
)


def test_stream_parser_approval_request():
    """Verify that StreamParser correctly parses tool_approval_request events with the actual wire protocol."""
    parser = StreamParser()
    # The actual wire protocol seen in logs: {"type":"CUSTOM","name":"tool_approval_request","value":{...}}
    chunk = (
        'data: {"type": "CUSTOM", "name": "tool_approval_request", '
        '"value": {"approvalId": "req123", "toolName": "search", "args": {"q": "test"}, '
        '"decision": {"behavior": "ask", "reason": "Approval required", '
        '"reasonCode": "tool_requires_approval", "risk": "medium", "actions": []}}}'
        "\n\n"
    )
    events = list(parser.parse([chunk]))

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ApprovalRequest)
    assert event.request_id == "req123"
    assert event.tool_name == "search"
    assert event.args == {"q": "test"}
    assert event.decision is not None
    assert event.decision["reasonCode"] == "tool_requires_approval"


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


def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


def test_stream_parser_assembles_tool_call_from_agui_events():
    """TOOL_CALL_START/ARGS/END is the real wire shape: name + streamed args."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "call_1", '
                    '"toolCallName": "read_file"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "call_1", '
                    '"delta": "{\\"path\\": "}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "call_1", '
                    '"delta": "\\"/tmp/a.txt\\"}"}'
                ),
                _sse('{"type": "TOOL_CALL_END", "toolCallId": "call_1"}'),
            ]
        )
    )

    assert len(events) == 1
    call = events[0]
    assert isinstance(call, ToolCall)
    assert call.tool_name == "read_file"
    assert call.arguments == {"path": "/tmp/a.txt"}
    assert call.tool_call_id == "call_1"
    assert call.raw_arguments == '{"path": "/tmp/a.txt"}'


def test_stream_parser_tool_result_uses_content_and_call_id():
    """TOOL_CALL_RESULT carries `content` and correlates by toolCallId."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "call_1", '
                    '"toolCallName": "read_file"}'
                ),
                _sse('{"type": "TOOL_CALL_END", "toolCallId": "call_1"}'),
                _sse(
                    '{"type": "TOOL_CALL_RESULT", "messageId": "m1", '
                    '"toolCallId": "call_1", "content": "file contents"}'
                ),
            ]
        )
    )

    assert [type(e) for e in events] == [ToolCall, ToolOutput]
    output = events[1]
    assert output.tool_name == "read_file"
    assert output.output == "file contents"
    assert output.tool_call_id == "call_1"


def test_stream_parser_result_closes_call_without_end():
    """A result implies the call closed even if TOOL_CALL_END never arrived."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "call_9", '
                    '"toolCallName": "bash_execute"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "call_9", '
                    '"delta": "{\\"content\\": \\"ls\\"}"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_RESULT", "toolCallId": "call_9", '
                    '"content": "a.txt"}'
                ),
            ]
        )
    )

    assert [type(e) for e in events] == [ToolCall, ToolOutput]
    assert events[0].arguments == {"content": "ls"}
    assert events[1].output == "a.txt"


def test_stream_parser_interleaves_parallel_tool_calls():
    """Args deltas are routed by toolCallId, not by arrival order."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "a", '
                    '"toolCallName": "first"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "b", '
                    '"toolCallName": "second"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "a", '
                    '"delta": "{\\"x\\": 1}"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "b", '
                    '"delta": "{\\"y\\": 2}"}'
                ),
                _sse('{"type": "TOOL_CALL_END", "toolCallId": "b"}'),
                _sse('{"type": "TOOL_CALL_END", "toolCallId": "a"}'),
            ]
        )
    )

    assert [(e.tool_name, e.arguments, e.tool_call_id) for e in events] == [
        ("second", {"y": 2}, "b"),
        ("first", {"x": 1}, "a"),
    ]


def test_stream_parser_emits_tool_call_once_per_call():
    """END then RESULT must not produce two ToolCall events."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                    '"toolCallName": "t"}'
                ),
                _sse('{"type": "TOOL_CALL_END", "toolCallId": "c"}'),
                _sse('{"type": "TOOL_CALL_RESULT", "toolCallId": "c", "content": ""}'),
                _sse('{"type": "AGENT_FINISHED"}'),
            ]
        )
    )

    assert sum(isinstance(e, ToolCall) for e in events) == 1


def test_stream_parser_flush_emits_unclosed_tool_call():
    """A stream that ends mid-call still reports the tool it started."""
    parser = StreamParser()

    streamed = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                    '"toolCallName": "web_search"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "c", '
                    '"delta": "{\\"q\\": \\"suzent\\"}"}'
                ),
            ]
        )
    )
    assert streamed == []

    flushed = list(parser.flush())
    assert len(flushed) == 1
    assert flushed[0].tool_name == "web_search"
    assert flushed[0].arguments == {"q": "suzent"}
    # Already emitted, so a second flush is a no-op.
    assert list(parser.flush()) == []


def test_stream_parser_run_error_flushes_open_tool_call():
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                    '"toolCallName": "t"}'
                ),
                _sse('{"type": "RUN_ERROR", "message": "boom"}'),
            ]
        )
    )

    assert [type(e) for e in events] == [ToolCall, ErrorEvent]
    assert events[1].message == "boom"


def test_stream_parser_tool_call_partial_args_keep_raw_text():
    """Truncated JSON yields empty arguments but preserves the raw text."""
    parser = StreamParser()

    list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                    '"toolCallName": "t"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "c", '
                    '"delta": "{\\"path\\": "}'
                ),
            ]
        )
    )
    call = list(parser.flush())[0]

    assert call.arguments == {}
    assert call.raw_arguments == '{"path": '
    assert call.format_arguments() == '{"path":'


def test_stream_parser_replayed_start_restarts_args():
    """Resume after approval replays START; args must not be concatenated."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                    '"toolCallName": "t"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "c", '
                    '"delta": "{\\"x\\": 1}"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                    '"toolCallName": "t"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_ARGS", "toolCallId": "c", '
                    '"delta": "{\\"x\\": 2}"}'
                ),
                _sse('{"type": "TOOL_CALL_END", "toolCallId": "c"}'),
            ]
        )
    )

    assert len(events) == 1
    assert events[0].arguments == {"x": 2}


def test_stream_parser_legacy_tool_field_names_still_work():
    """Older emitters send tool_name/args on START and `output` on RESULT."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "tool_name": "legacy_tool", '
                    '"args": {"a": 1}}'
                ),
                _sse('{"type": "TOOL_CALL_RESULT", "output": "done"}'),
            ]
        )
    )

    assert [type(e) for e in events] == [ToolCall, ToolOutput]
    assert events[0].tool_name == "legacy_tool"
    assert events[0].arguments == {"a": 1}
    assert events[1].tool_name == "legacy_tool"
    assert events[1].output == "done"


def test_stream_parser_tool_result_stringifies_structured_content():
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                    '"toolCallName": "t"}'
                ),
                _sse(
                    '{"type": "TOOL_CALL_RESULT", "toolCallId": "c", '
                    '"content": [{"type": "text", "text": "hi"}]}'
                ),
            ]
        )
    )

    output = events[-1]
    assert isinstance(output, ToolOutput)
    assert output.output == '[{"type": "text", "text": "hi"}]'


def test_stream_parser_legacy_stream_delta_tool_calls():
    """Legacy stream_delta keeps working and now parses string arguments."""
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "stream_delta", "data": {"tool_calls": [{"id": "t1", '
                    '"function": {"name": "calc", "arguments": "{\\"x\\": 1}"}}]}}'
                )
            ]
        )
    )

    assert len(events) == 1
    assert events[0].tool_name == "calc"
    assert events[0].arguments == {"x": 1}
    assert events[0].tool_call_id == "t1"


def test_stream_parser_legacy_tool_output_event():
    parser = StreamParser()

    events = list(
        parser.parse(
            [
                _sse(
                    '{"type": "tool_output", "data": {"tool_call_id": "t1", '
                    '"tool_call": {"name": "calc"}, "output": "42"}}'
                )
            ]
        )
    )

    assert len(events) == 1
    assert events[0].tool_name == "calc"
    assert events[0].output == "42"
    assert events[0].tool_call_id == "t1"


def test_stream_parser_does_not_log_raw_tool_arguments():
    """Malformed args must not reach the logs: they can carry secrets/PII."""
    from suzent.logger import logger

    records: list[str] = []
    sink_id = logger.add(records.append, level="DEBUG")
    try:
        parser = StreamParser()
        list(
            parser.parse(
                [
                    _sse(
                        '{"type": "TOOL_CALL_START", "toolCallId": "c", '
                        '"toolCallName": "bash_execute"}'
                    ),
                    _sse(
                        '{"type": "TOOL_CALL_ARGS", "toolCallId": "c", '
                        '"delta": "{\\"sk-secret-token\\": "}'
                    ),
                ]
            )
        )
        call = list(parser.flush())[0]
    finally:
        logger.remove(sink_id)

    assert call.arguments == {}
    assert call.raw_arguments  # still available to the caller, just not logged
    logged = "".join(records)
    assert "sk-secret-token" not in logged
    assert "Unparseable tool call arguments" in logged
