import json
from types import SimpleNamespace

import httpx
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from suzent.core import model_factory
from suzent.core.prompt_cache import (
    CacheRouting,
    PromptCacheRoutingCapability,
    cache_key_for,
    cache_routing_settings,
    register_cache_routing,
)
from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID


def _recording_model(seen: list) -> FunctionModel:
    def respond(_messages, info: AgentInfo) -> ModelResponse:
        seen.append(dict(info.model_settings or {}))
        return ModelResponse(parts=[TextPart("ok")])

    return FunctionModel(respond)


def test_first_party_anthropic_uses_automatic_caching() -> None:
    settings = model_factory.anthropic_cache_settings(None)

    assert settings["anthropic_cache"] is True
    assert settings["anthropic_cache_instructions"] is True
    assert settings["anthropic_cache_tool_definitions"] is True
    assert "anthropic_cache_messages" not in settings


def test_compatible_anthropic_endpoint_uses_explicit_breakpoints() -> None:
    settings = model_factory.anthropic_cache_settings("https://gateway.example/v1")

    assert settings["anthropic_cache_messages"] is True
    assert "anthropic_cache" not in settings


def test_anthropic_model_carries_cache_settings() -> None:
    model = model_factory._create_anthropic_model(
        "claude-sonnet-5-5", "test-key", PROVIDER_REGISTRY_BY_ID["anthropic"]
    )

    assert model.settings["anthropic_cache"] is True


def test_only_first_party_openai_gets_a_prompt_cache_key() -> None:
    openai = model_factory._create_openai_model(
        "gpt-5.6", "test-key", PROVIDER_REGISTRY_BY_ID["openai"]
    )
    compatible = model_factory._create_openai_model(
        "qwen-max", "test-key", PROVIDER_REGISTRY_BY_ID["dashscope"]
    )

    assert cache_routing_settings(openai, "chat-1") == {
        "openai_prompt_cache_key": "chat-1"
    }
    assert cache_routing_settings(compatible, "chat-1") is None


def test_openai_lookalike_host_gets_no_prompt_cache_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com.proxy.example/v1")
    proxied = model_factory._create_openai_model(
        "gpt-5.6", "test-key", PROVIDER_REGISTRY_BY_ID["openai"]
    )

    assert cache_routing_settings(proxied, "chat-1") is None


def test_long_chat_ids_hash_to_a_stable_64_char_key() -> None:
    long_id = "a2a:device-1234567890:" + "c" * 80

    key = cache_key_for(long_id)

    assert len(key) == 64
    assert key == cache_key_for(long_id)
    assert key != cache_key_for(long_id + "x")
    assert cache_key_for("chat-1") == "chat-1"


def test_session_header_keeps_existing_extra_headers() -> None:
    model = _recording_model([])
    register_cache_routing(model, CacheRouting.SESSION_HEADER)

    settings = cache_routing_settings(
        model, "chat-1", {"extra_headers": {"x-trace": "1"}, "temperature": 0}
    )

    assert settings == {
        "extra_headers": {"x-trace": "1", "session_id": "chat-1"},
        "temperature": 0,
    }


def test_missing_chat_id_leaves_settings_untouched() -> None:
    model = _recording_model([])
    register_cache_routing(model, CacheRouting.PROMPT_CACHE_KEY)

    assert cache_routing_settings(model, "", {"temperature": 0}) == {"temperature": 0}


async def test_capability_keys_each_request_by_the_served_chat() -> None:
    seen: list = []
    model = _recording_model(seen)
    register_cache_routing(model, CacheRouting.PROMPT_CACHE_KEY)
    agent = Agent(model, capabilities=[PromptCacheRoutingCapability()])

    await agent.run("hi", deps=SimpleNamespace(chat_id="chat-a"))
    await agent.run("hi", deps=SimpleNamespace(chat_id="chat-b"))

    assert [s.get("openai_prompt_cache_key") for s in seen] == ["chat-a", "chat-b"]


async def test_capability_ignores_models_without_routing() -> None:
    seen: list = []
    agent = Agent(_recording_model(seen), capabilities=[PromptCacheRoutingCapability()])

    await agent.run("hi", deps=SimpleNamespace(chat_id="chat-a"))

    assert "openai_prompt_cache_key" not in seen[0]
    assert "extra_headers" not in seen[0]


async def test_session_header_reaches_the_wire() -> None:
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
            },
        )

    client = AsyncOpenAI(
        api_key="test",
        base_url="https://example.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    model = OpenAIChatModel("gpt", provider=OpenAIProvider(openai_client=client))
    register_cache_routing(model, CacheRouting.SESSION_HEADER)
    agent = Agent(model, capabilities=[PromptCacheRoutingCapability()])

    await agent.run("hi", deps=SimpleNamespace(chat_id="chat-a"))

    assert captured[0].headers["session_id"] == "chat-a"
    assert "prompt_cache_key" not in json.loads(captured[0].content)


async def test_anthropic_request_marks_cache_breakpoints() -> None:
    import httpx2
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
    from pydantic_ai.providers.anthropic import AnthropicProvider

    captured: list[dict] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        captured.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "m1",
                "type": "message",
                "role": "assistant",
                "model": "claude",
                "content": [{"type": "text", "text": "ok"}],
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
    agent = Agent(model, instructions="Be brief.")

    @agent.tool_plain
    def lookup(term: str) -> str:
        return term

    await agent.run("hi")

    body = captured[0]
    assert body["cache_control"]["type"] == "ephemeral"
    assert body["system"][-1]["cache_control"]["type"] == "ephemeral"
    assert body["tools"][-1]["cache_control"]["type"] == "ephemeral"
