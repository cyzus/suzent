import asyncio
import json

from suzent.channels.base import MESSAGE_BREAK
from suzent.core.social_brain import channel_text_stream


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _parts(chunks: list[str], on_reaction=None) -> list:
    queue: asyncio.Queue = asyncio.Queue()
    for chunk in chunks:
        queue.put_nowait(chunk)
    queue.put_nowait(None)
    return [part async for part in channel_text_stream(queue, on_reaction)]


def _messages(parts: list) -> list[str]:
    """Group streamed parts into the chat messages a channel would send."""
    messages, current = [], ""
    for part in parts:
        if part is MESSAGE_BREAK:
            if current:
                messages.append(current)
            current = ""
        else:
            current += part
    if current:
        messages.append(current)
    return messages


async def _collect(chunks: list[str]) -> str:
    return "".join(p for p in await _parts(chunks) if p is not MESSAGE_BREAK)


def _tool_call(call_id: str, tool_name: str, metadata: dict) -> list[str]:
    result = {"success": True, "metadata": metadata}
    return [
        _sse(
            {
                "type": "TOOL_CALL_START",
                "toolCallId": call_id,
                "toolCallName": tool_name,
            }
        ),
        _sse({"type": "TOOL_CALL_END", "toolCallId": call_id}),
        _sse(
            {
                "type": "TOOL_CALL_RESULT",
                "toolCallId": call_id,
                "content": json.dumps(result),
            }
        ),
    ]


def _send_message_call(call_id: str, texts: list[str]) -> list[str]:
    return _tool_call(call_id, "send_message", {"regent_messages": texts})


async def test_streams_plain_text_deltas():
    text = await _collect(
        [
            _sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "Hello "}),
            _sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "there"}),
        ]
    )
    assert text == "Hello there"


async def test_streams_regent_send_message_when_final_answer_is_empty():
    text = await _collect(_send_message_call("c1", ["Looking now.", "Two failed."]))
    assert "Looking now." in text
    assert "Two failed." in text


async def test_keeps_regent_messages_in_order_with_final_text():
    text = await _collect(
        [
            *_send_message_call("c1", ["On it."]),
            _sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "Done."}),
        ]
    )
    assert text.index("On it.") < text.index("Done.")


async def test_ignores_other_tool_results():
    text = await _collect(
        [
            _sse(
                {
                    "type": "TOOL_CALL_START",
                    "toolCallId": "c2",
                    "toolCallName": "web_search",
                }
            ),
            _sse(
                {
                    "type": "TOOL_CALL_RESULT",
                    "toolCallId": "c2",
                    "content": json.dumps(
                        {"success": True, "metadata": {"regent_messages": ["x"]}}
                    ),
                }
            ),
        ]
    )
    assert text == ""


async def test_each_regent_message_is_its_own_chat_message():
    parts = await _parts(
        [
            _sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "Let me check."}),
            *_send_message_call("c1", ["Looking now.", "Two failed."]),
            _sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "All fixed."}),
        ]
    )
    assert _messages(parts) == [
        "Let me check.",
        "Looking now.",
        "Two failed.",
        "All fixed.",
    ]


async def test_regent_reaction_reaches_callback():
    seen: list[str] = []

    async def on_reaction(emoji: str) -> None:
        seen.append(emoji)

    parts = await _parts(
        _tool_call("r1", "react_to_message", {"regent_reaction": "👍"}),
        on_reaction,
    )
    assert seen == ["👍"]
    assert _messages(parts) == []
