import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from suzent.core.agent_deps import AgentDeps
from suzent.core.chat_processor import _rebuild_display_messages
from suzent.core.focal_agent import FOCAL_CHAT_ID, FOCAL_TOOL_NAMES
from suzent.core.heartbeat import turn_acted
from suzent.tools.focal.conversation import FocalMessageTool, FocalReactionTool


def context(chat_id: str = FOCAL_CHAT_ID, prompt: str = "hello") -> SimpleNamespace:
    return SimpleNamespace(
        deps=AgentDeps(chat_id=chat_id),
        messages=[ModelRequest(parts=[UserPromptPart(content=prompt)])],
    )


@pytest.mark.parametrize("tool", [FocalMessageTool, FocalReactionTool])
async def test_only_regent_can_deliver(tool: type) -> None:
    args = {"messages": ["hello"]} if tool is FocalMessageTool else {"emoji": "👍"}
    assert not (await tool().forward(context("project"), **args)).success
    assert tool.name in FOCAL_TOOL_NAMES
    assert not tool.group and not tool.deferrable


@pytest.mark.parametrize("messages", [[], [" "], ["x" * 4001], ["hi"] * 5])
async def test_invalid_messages_do_not_deliver(messages: list[str]) -> None:
    assert not (await FocalMessageTool().forward(context(), messages)).success


async def test_deliveries_survive_display_rebuild_and_count_as_heartbeat_actions() -> (
    None
):
    ctx = context()
    for tool, args in [
        (FocalMessageTool(), {"messages": [" Looking now. ", "Two tests failed."]}),
        (FocalReactionTool(), {"emoji": "👀"}),
    ]:
        result = await tool.forward(ctx, **args)
        assert result.success
        history = ctx.messages + [
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=tool.tool_name, args=args, tool_call_id="delivery"
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name=tool.tool_name,
                        tool_call_id="delivery",
                        content=result,
                    )
                ]
            ),
        ]
        assert turn_acted(history)
        rebuilt = _rebuild_display_messages(history)
        part = rebuilt[1]["parts"][0]
        assert part["toolCallId"] == "delivery"
        assert json.loads(part["output"])["metadata"] == result.metadata


async def test_reaction_can_be_replaced_or_removed() -> None:
    for emoji in ["❤️", "✅", ""]:
        result = await FocalReactionTool().forward(context(), emoji)
        assert result.success
        assert result.metadata["regent_reaction"] == emoji


async def test_reaction_rejects_empty_turn_and_invalid_emoji() -> None:
    assert not (await FocalReactionTool().forward(context(prompt=""), "👍")).success
    assert not (await FocalReactionTool().forward(context(), "arbitrary text")).success


async def test_background_reply_includes_sent_messages_once() -> None:
    from suzent.core.stream_parser import StreamParser, TextChunk

    result = await FocalMessageTool().forward(context(), ["Hello", "Checking now"])
    frames = [
        {
            "type": "TOOL_CALL_START",
            "toolCallName": "send_message",
            "toolCallId": "send",
        },
        {
            "type": "TOOL_CALL_RESULT",
            "toolCallId": "send",
            "content": result.model_dump(mode="json"),
        },
        {
            "type": "TOOL_CALL_RESULT",
            "toolCallId": "send",
            "content": result.model_dump(mode="json"),
        },
    ]
    parser = StreamParser()
    text = "".join(
        event.content
        for frame in frames
        for event in parser.parse(iter(["data: " + json.dumps(frame) + "\n\n"]))
        if isinstance(event, TextChunk)
    )
    assert text.strip() == "Hello\n\nChecking now"


async def test_reaction_does_not_target_a_background_trigger() -> None:
    from suzent.core.system_reminder import wrap_in_system_reminder

    ctx = context(
        prompt=wrap_in_system_reminder("Check projects", display_trigger="Wake up")
    )
    assert not (await FocalReactionTool().forward(ctx, "👀")).success
