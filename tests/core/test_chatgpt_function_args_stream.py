"""Parallel function calls from the ChatGPT backend keep their arguments.

For several calls in one response the backend streams no
``function_call_arguments.delta``; the arguments only appear in the done
events. pydantic-ai builds arguments from the deltas, so without the rewrite
every parallel call reached its tool as ``{}`` and failed validation.
"""

import json

import httpx
import pytest

from suzent.core.model_factory import _ChatGPTFunctionArgsStream, _ChatGPTHTTPClient


def _sse(event: dict) -> bytes:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


def _response(status: str) -> dict:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-test",
        "status": status,
        "output": [],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


def _parallel_calls_without_deltas(cities: list[str]) -> list[dict]:
    events: list[dict] = [
        {"type": "response.created", "response": _response("in_progress")}
    ]
    for index, city in enumerate(cities):
        item = {
            "type": "function_call",
            "id": f"fc_{index}",
            "call_id": f"call_{index}",
            "name": "get_weather",
            "status": "in_progress",
        }
        arguments = json.dumps({"city": city})
        events += [
            {
                "type": "response.output_item.added",
                "output_index": index,
                "item": {**item, "arguments": ""},
            },
            {
                "type": "response.function_call_arguments.done",
                "item_id": f"fc_{index}",
                "output_index": index,
                "arguments": arguments,
            },
            {
                "type": "response.output_item.done",
                "output_index": index,
                "item": {**item, "arguments": arguments, "status": "completed"},
            },
        ]
    events.append({"type": "response.completed", "response": _response("completed")})
    return events


class _Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


async def _rewritten(events: list[dict], chunk_size: int | None = None) -> list[dict]:
    raw = b"".join(_sse(event) for event in events)
    chunks = (
        [raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)]
        if chunk_size
        else [raw]
    )
    out = b"".join(
        [chunk async for chunk in _ChatGPTFunctionArgsStream(_Chunks(chunks))]
    )
    return [
        json.loads(line[5:]) for line in out.splitlines() if line.startswith(b"data:")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [None, 7])
async def test_each_parallel_call_gets_its_arguments_once_before_done(chunk_size):
    events = await _rewritten(
        _parallel_calls_without_deltas(["Paris", "Tokyo"]), chunk_size
    )

    deltas = [
        e for e in events if e["type"] == "response.function_call_arguments.delta"
    ]
    assert [(d["item_id"], json.loads(d["delta"])) for d in deltas] == [
        ("fc_0", {"city": "Paris"}),
        ("fc_1", {"city": "Tokyo"}),
    ]
    types = [e["type"] for e in events]
    for delta in deltas:
        position = events.index(delta)
        assert types[position + 1] == "response.function_call_arguments.done"


@pytest.mark.asyncio
async def test_calls_that_streamed_their_arguments_are_left_alone():
    item = {
        "type": "function_call",
        "id": "fc_0",
        "call_id": "c",
        "name": "get_weather",
    }
    streamed = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {**item, "arguments": ""},
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_0",
            "output_index": 0,
            "delta": '{"city": "Paris"}',
        },
        {
            "type": "response.function_call_arguments.done",
            "item_id": "fc_0",
            "output_index": 0,
            "arguments": '{"city": "Paris"}',
        },
    ]
    assert await _rewritten(streamed) == streamed


@pytest.mark.asyncio
async def test_arguments_only_in_item_done_are_recovered_too():
    events = [
        e
        for e in _parallel_calls_without_deltas(["Paris"])
        if e["type"] != "response.function_call_arguments.done"
    ]
    deltas = [
        e
        for e in await _rewritten(events)
        if e["type"] == "response.function_call_arguments.delta"
    ]
    assert [json.loads(d["delta"]) for d in deltas] == [{"city": "Paris"}]


@pytest.mark.asyncio
async def test_pydantic_ai_receives_every_parallel_calls_arguments():
    from openai import AsyncOpenAI
    from pydantic_ai import Agent
    from pydantic_ai.messages import ToolCallPart
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            events = _parallel_calls_without_deltas(["Paris", "Tokyo", "London"])
        else:
            events = [
                {"type": "response.created", "response": _response("in_progress")},
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "type": "message",
                        "id": "m",
                        "role": "assistant",
                        "content": [],
                        "status": "in_progress",
                    },
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": "m",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "done",
                },
                {"type": "response.completed", "response": _response("completed")},
            ]
        # A streamed body, as the live endpoint sends: `content=` would be
        # pre-read and bypass the response stream entirely.
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_Chunks([_sse(event) for event in events]),
        )

    http_client = _ChatGPTHTTPClient(
        "instructions", transport=httpx.MockTransport(handler)
    )
    client = AsyncOpenAI(
        api_key="test", base_url="https://chatgpt.test/v1", http_client=http_client
    )
    model = OpenAIResponsesModel(
        "gpt-test", provider=OpenAIProvider(openai_client=client)
    )

    seen: list[str] = []

    def get_weather(city: str) -> str:
        """Return the weather for a city."""
        seen.append(city)
        return "sunny"

    agent = Agent(model, tools=[get_weather], retries=0)
    async with agent.run_stream("weather?") as run:
        await run.get_output()
        messages = run.all_messages()

    # Parallel calls run concurrently, so only the set of cities is fixed.
    assert sorted(seen) == ["London", "Paris", "Tokyo"]
    args = [
        part.args_as_dict()
        for message in messages
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert args == [{"city": "Paris"}, {"city": "Tokyo"}, {"city": "London"}]
