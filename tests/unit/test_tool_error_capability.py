"""A tool that raises fails its call instead of ending the turn.

pydantic-ai re-raises a tool's exception by default, so any tool that did not
catch its own errors (crawler, database, a dropped MCP connection) aborted the
whole run and left its call without a result.
"""

import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from suzent.tools.capability import ToolErrorCapability


def _call_then_answer(tool_name: str):
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if not returns:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name=tool_name, args={}, tool_call_id="call-1")
                ]
            )
        return ModelResponse(parts=[TextPart(content=f"saw: {returns[0].content}")])

    return FunctionModel(model)


def _tool_returns(result) -> list[ToolReturnPart]:
    return [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


async def test_a_raising_tool_becomes_a_failed_call_and_the_turn_continues():
    agent = Agent(_call_then_answer("fetch"), capabilities=[ToolErrorCapability()])

    @agent.tool_plain
    def fetch() -> str:
        raise ConnectionError("crawler unreachable")

    result = await agent.run("go")

    (returned,) = _tool_returns(result)
    assert returned.outcome == "failed"
    assert "ConnectionError: crawler unreachable" in str(returned.content)
    assert result.output.startswith("saw: ")


async def test_without_it_the_same_tool_aborts_the_run():
    agent = Agent(_call_then_answer("fetch"))

    @agent.tool_plain
    def fetch() -> str:
        raise ConnectionError("crawler unreachable")

    with pytest.raises(ConnectionError):
        await agent.run("go")


async def test_a_successful_tool_is_untouched():
    agent = Agent(_call_then_answer("fetch"), capabilities=[ToolErrorCapability()])

    @agent.tool_plain
    def fetch() -> str:
        return "page"

    (returned,) = _tool_returns(await agent.run("go"))
    assert returned.outcome == "success"
    assert returned.content == "page"


async def test_cancellation_still_stops_the_run():
    agent = Agent(_call_then_answer("wait"), capabilities=[ToolErrorCapability()])

    @agent.tool_plain
    async def wait() -> str:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await agent.run("go")


async def test_a_long_error_is_cut_short():
    agent = Agent(_call_then_answer("fetch"), capabilities=[ToolErrorCapability()])

    @agent.tool_plain
    def fetch() -> str:
        raise RuntimeError("x" * 10_000)

    (returned,) = _tool_returns(await agent.run("go"))
    assert len(str(returned.content)) < 2200
