"""Compaction summaries written on the conversation's cached prefix, and the
background summary a finished turn prepares for the next compaction."""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

import suzent.core.context_compressor as cc
from suzent.config import CONFIG
from suzent.core.agent_serializer import deserialize_state, serialize_state
from suzent.core.context_compressor import (
    CACHED_SUMMARY_PROMPT,
    REQUIRED_SECTIONS,
    ContextCompressor,
    ToolResultTrimmer,
    history_fingerprint,
    make_compaction_history_processor,
    schedule_precompaction,
    summarize_on_cached_prefix,
)
from suzent.core.prompt_cache import (
    CacheRouting,
    ForkPrefixCapability,
    PromptCacheRoutingCapability,
    RequestRecorderCapability,
    register_cache_routing,
)

SUMMARY = "\n".join(f"{section}\nnotes" for section in REQUIRED_SECTIONS)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", lambda p: None)
    monkeypatch.setattr(CONFIG, "compaction_keep_recent_turns", 1, raising=False)
    monkeypatch.setattr(CONFIG, "compaction_reuse_prompt_cache", True, raising=False)
    monkeypatch.setattr(CONFIG, "context_precompaction_trigger", 0.70, raising=False)
    monkeypatch.setattr(CONFIG, "memory_enabled", False, raising=False)
    cc.reset_compaction_suppression()
    cc.discard_precompaction()
    yield
    cc.reset_compaction_suppression()
    cc.discard_precompaction()


class _FailingClient:
    """Extraction-model client that must not be reached."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, **_kwargs) -> str:
        self.calls += 1
        return f"<summary>{SUMMARY}</summary>"


def _agent(sent: list, replies: list) -> Agent:
    """An agent whose requests are recorded; streamed requests are summaries."""

    def respond(messages, info: AgentInfo) -> ModelResponse:
        sent.append(("run", list(messages), info))
        return ModelResponse(parts=[TextPart("done")])

    async def stream(messages, info: AgentInfo):
        sent.append(("summary", list(messages), info))
        reply = replies.pop(0)
        if isinstance(reply, DeltaToolCall):
            yield {0: reply}
        else:
            yield reply

    model = FunctionModel(respond, stream_function=stream)
    register_cache_routing(model, CacheRouting.PROMPT_CACHE_KEY)
    agent = Agent(
        model,
        deps_type=SimpleNamespace,
        capabilities=[
            PromptCacheRoutingCapability(),
            ForkPrefixCapability(),
            RequestRecorderCapability(),
        ],
    )

    @agent.instructions
    def persona(ctx) -> str:
        return f"You are serving {ctx.deps.chat_id}."

    @agent.tool_plain
    def lookup() -> str:
        """Look something up."""
        return "found"

    return agent


async def _run(agent: Agent, chat_id: str, history: list | None = None) -> list:
    result = await agent.run(
        "start", deps=SimpleNamespace(chat_id=chat_id), message_history=history
    )
    return result.all_messages()


async def test_summary_repeats_the_conversations_own_request() -> None:
    sent: list = []
    agent = _agent(sent, [f"<summary>{SUMMARY}</summary>"])
    history = await _run(agent, "cache-a")

    body = await summarize_on_cached_prefix("cache-a", history, 1, 200_000)

    assert body == SUMMARY
    (_, run_messages, run_info), (_, summary_messages, summary_info) = sent
    assert summary_info.instructions == run_info.instructions
    assert summary_info.function_tools == run_info.function_tools
    assert summary_info.model_settings["openai_prompt_cache_key"] == "cache-a"
    # The same request as before, with the instruction added at its very end.
    assert summary_messages[:-1] == run_messages[:-1]
    assert summary_messages[-1].parts[:-1] == run_messages[-1].parts
    assert summary_messages[-1].parts[-1].content == CACHED_SUMMARY_PROMPT


async def test_history_the_latest_request_did_not_send_is_not_covered() -> None:
    sent: list = []
    agent = _agent(sent, [f"<summary>{SUMMARY}</summary>"])
    history = await _run(agent, "cache-cover")
    rewritten = [ModelRequest(parts=[UserPromptPart(content="other")])] + history[1:]

    assert await summarize_on_cached_prefix("cache-cover", rewritten, 1, 200_000) == ""
    assert (
        await summarize_on_cached_prefix(
            "cache-cover", history + history, len(history) + 1, 200_000
        )
        == ""
    )
    assert [kind for kind, *_ in sent] == ["run"]


async def test_tool_call_reply_is_retried_with_a_correction() -> None:
    sent: list = []
    agent = _agent(
        sent,
        [
            DeltaToolCall(name="lookup", json_args="{}"),
            f"<summary>{SUMMARY}</summary>",
        ],
    )
    history = await _run(agent, "cache-retry")

    body = await summarize_on_cached_prefix("cache-retry", history, 1, 200_000)

    assert body == SUMMARY
    retry_prompt = sent[-1][1][-1].parts[-1].content
    assert "Tools are unavailable" in retry_prompt


async def test_no_cached_request_means_no_summary() -> None:
    history = [ModelRequest(parts=[UserPromptPart(content="hi")])]

    assert await summarize_on_cached_prefix("never-ran", history, 1, 200_000) == ""


async def test_history_too_close_to_the_window_is_not_resent() -> None:
    sent: list = []
    agent = _agent(sent, [f"<summary>{SUMMARY}</summary>"])
    result = await agent.run("x " * 5000, deps=SimpleNamespace(chat_id="cache-full"))
    history = result.all_messages()

    assert await summarize_on_cached_prefix("cache-full", history, 1, 1000) == ""
    assert [kind for kind, *_ in sent] == ["run"]


def _long_history(chat_turns: int = 6) -> list:
    messages: list = [ModelRequest(parts=[UserPromptPart(content="opening")])]
    for i in range(chat_turns):
        messages += [
            ModelResponse(
                parts=[ToolCallPart(tool_name="read", args="{}", tool_call_id=f"t{i}")]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="read", content="x" * 4000, tool_call_id=f"t{i}"
                    )
                ]
            ),
            ModelResponse(parts=[TextPart(f"step {i}")]),
            ModelRequest(parts=[UserPromptPart(content=f"go on {i}")]),
        ]
    return messages


async def test_compression_prefers_the_cached_prefix(monkeypatch) -> None:
    sent: list = []
    agent = _agent(sent, [f"<summary>{SUMMARY}</summary>"])
    history = await _run(agent, "cache-compress", _long_history()[:-1])
    client = _FailingClient()
    compressor = ContextCompressor(llm_client=client, chat_id="cache-compress")

    out = await compressor._perform_compression(history)

    assert client.calls == 0
    assert len(out) < len(history)
    assert sent[-1][0] == "summary"


async def test_compression_falls_back_without_a_cached_request() -> None:
    client = _FailingClient()
    compressor = ContextCompressor(llm_client=client, chat_id="no-cache")

    history = _long_history()
    out = await compressor._perform_compression(history)

    assert client.calls >= 1
    assert len(out) < len(history)


async def test_cache_reuse_can_be_turned_off(monkeypatch) -> None:
    monkeypatch.setattr(CONFIG, "compaction_reuse_prompt_cache", False, raising=False)
    sent: list = []
    agent = _agent(sent, [f"<summary>{SUMMARY}</summary>"])
    history = await _run(agent, "cache-off", _long_history()[:-1])
    client = _FailingClient()
    compressor = ContextCompressor(llm_client=client, chat_id="cache-off")

    await compressor._perform_compression(history)

    assert client.calls >= 1
    assert [kind for kind, *_ in sent] == ["run"]


def test_fingerprint_ignores_trimmed_tool_output_and_survives_a_reload() -> None:
    history = _long_history()
    trimmed = ToolResultTrimmer._rewrite_old_results(
        history, ToolResultTrimmer._hard, stepped=False
    )
    reloaded = deserialize_state(serialize_state(history))["message_history"]

    assert trimmed[2].parts[0].content != history[2].parts[0].content
    assert history_fingerprint(trimmed) == history_fingerprint(history)
    assert history_fingerprint(reloaded) == history_fingerprint(history)

    edited = list(history)
    edited[4] = ModelRequest(parts=[UserPromptPart(content="something else")])
    assert history_fingerprint(edited) != history_fingerprint(history)


def _prepared_summaries(monkeypatch) -> list:
    """Stub the summary writer; returns the histories it was asked about."""
    asked: list = []

    async def fake(self, messages, end_index, focus=None):
        asked.append((list(messages), end_index))
        return SUMMARY

    monkeypatch.setattr(ContextCompressor, "_summarize_history", fake)
    return asked


async def test_turn_below_the_threshold_prepares_nothing(monkeypatch) -> None:
    monkeypatch.setattr(CONFIG, "max_context_tokens", 1_000_000, raising=False)
    asked = _prepared_summaries(monkeypatch)

    assert not schedule_precompaction("small", _long_history())
    assert asked == []


async def test_prepared_summary_is_applied_by_the_next_compaction(monkeypatch) -> None:
    monkeypatch.setattr(CONFIG, "max_context_tokens", 7_500, raising=False)
    monkeypatch.setattr(CONFIG, "context_compaction_trigger", 0.80, raising=False)
    asked = _prepared_summaries(monkeypatch)

    async def must_not_run(self, *args, **kwargs):
        raise AssertionError("a fresh summary was written")

    turn_end = _long_history()
    assert schedule_precompaction("prep", turn_end)
    await asyncio.sleep(0)

    # The next turn's prompt takes the history over the trigger.
    next_turn = turn_end + [ModelRequest(parts=[UserPromptPart(content="y " * 200)])]
    monkeypatch.setattr(ContextCompressor, "_perform_compression", must_not_run)
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="prep", user_id="u"))

    out = await make_compaction_history_processor()(ctx, next_turn)

    assert len(asked) == 1
    assert len(out) < len(next_turn)
    assert out[-1] is next_turn[-1]
    assert SUMMARY in out[2].parts[0].content
    assert "prep" not in cc._PRECOMPACTIONS


async def test_summary_for_another_history_is_discarded(monkeypatch) -> None:
    monkeypatch.setattr(CONFIG, "max_context_tokens", 7_500, raising=False)
    _prepared_summaries(monkeypatch)
    assert schedule_precompaction("stale", _long_history())

    rewritten = _long_history()
    rewritten[4] = ModelRequest(parts=[UserPromptPart(content="retried")])
    compressor = ContextCompressor(llm_client=_FailingClient(), chat_id="stale")

    assert await compressor.take_precompaction(rewritten) is None


async def test_a_still_useful_summary_is_not_written_again(monkeypatch) -> None:
    monkeypatch.setattr(CONFIG, "max_context_tokens", 7_500, raising=False)
    asked = _prepared_summaries(monkeypatch)
    history = _long_history()
    assert schedule_precompaction("again", history)
    await asyncio.sleep(0)

    longer = history + [
        ModelResponse(parts=[TextPart("answer")]),
        ModelRequest(parts=[UserPromptPart(content="one more")]),
    ]
    assert not schedule_precompaction("again", longer)
    assert len(asked) == 1


async def test_pending_summary_is_awaited_rather_than_started_twice(
    monkeypatch,
) -> None:
    monkeypatch.setattr(CONFIG, "max_context_tokens", 7_500, raising=False)
    release = asyncio.Event()

    async def slow(self, messages, end_index, focus=None):
        await release.wait()
        return SUMMARY

    monkeypatch.setattr(ContextCompressor, "_summarize_history", slow)
    history = _long_history()
    assert schedule_precompaction("slow", history)
    compressor = ContextCompressor(llm_client=_FailingClient(), chat_id="slow")
    current = history + [ModelRequest(parts=[UserPromptPart(content="now")])]

    waiting = asyncio.create_task(compressor.take_precompaction(current))
    await asyncio.sleep(0)
    assert not waiting.done()
    release.set()

    out = await waiting
    assert out is not None and len(out) < len(current)


async def test_anthropic_summary_request_keeps_the_cached_prefix() -> None:
    """On the wire, the summary request repeats the turn's system, tools and
    messages, so Anthropic serves them from cache."""
    import json

    import httpx2
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
    from pydantic_ai.providers.anthropic import AnthropicProvider

    from suzent.core import model_factory

    bodies: list[dict] = []

    def sse(text: str) -> str:
        events = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "m2",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude",
                        "content": [],
                        "stop_reason": None,
                        "usage": {
                            "input_tokens": 5,
                            "cache_read_input_tokens": 900,
                            "output_tokens": 1,
                        },
                    },
                },
            ),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 50},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
        return "".join(
            f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events
        )

    def handle(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("stream"):
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse(f"<summary>{SUMMARY}</summary>"),
            )
        return httpx2.Response(
            200,
            json={
                "id": "m1",
                "type": "message",
                "role": "assistant",
                "model": "claude",
                "content": [{"type": "text", "text": "done"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = AsyncAnthropic(
        api_key="test",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    model = AnthropicModel(
        "claude",
        provider=AnthropicProvider(anthropic_client=client),
        settings=AnthropicModelSettings(**model_factory.anthropic_cache_settings(None)),
    )
    agent = Agent(
        model,
        deps_type=SimpleNamespace,
        instructions="Be brief.",
        capabilities=[
            PromptCacheRoutingCapability(),
            ForkPrefixCapability(),
            RequestRecorderCapability(),
        ],
    )

    @agent.tool_plain
    def lookup(term: str) -> str:
        return term

    result = await agent.run("hi", deps=SimpleNamespace(chat_id="wire"))
    history = result.all_messages()

    body = await summarize_on_cached_prefix("wire", history, 1, 200_000)

    assert body == SUMMARY
    turn, summary = bodies
    assert summary["system"] == turn["system"]
    assert summary["tools"] == turn["tools"]
    assert summary.get("tool_choice") == turn.get("tool_choice")
    assert summary["cache_control"] == turn["cache_control"]
    # Every block the turn sent comes back unchanged, then the instruction.
    assert summary["messages"][:-1] == turn["messages"][:-1]
    assert summary["messages"][-1]["content"][:-1] == turn["messages"][-1]["content"]
    assert summary["messages"][-1]["content"][-1]["text"] == CACHED_SUMMARY_PROMPT


async def test_timeout_while_waiting_for_a_prepared_summary_is_not_swallowed(
    monkeypatch,
) -> None:
    monkeypatch.setattr(CONFIG, "max_context_tokens", 7_500, raising=False)
    started_fresh: list = []

    async def never(self, messages, end_index, focus=None):
        await asyncio.Event().wait()

    async def fresh(self, *args, **kwargs):
        started_fresh.append(True)
        return args[0]

    monkeypatch.setattr(ContextCompressor, "_summarize_history", never)
    monkeypatch.setattr(ContextCompressor, "_perform_compression", fresh)
    history = _long_history()
    assert schedule_precompaction("timeout", history)
    current = history + [ModelRequest(parts=[UserPromptPart(content="y " * 200)])]
    monkeypatch.setattr(CONFIG, "compaction_timeout_seconds", 0.05, raising=False)
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="timeout", user_id="u"))

    out = await make_compaction_history_processor()(ctx, current)

    assert out is current
    assert started_fresh == []
