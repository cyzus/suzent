import json
from unittest.mock import AsyncMock, patch

import httpx
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.native_tools import WebSearchTool
from pydantic_ai.native_tools._tool_search import ToolSearchTool

from suzent.core import model_factory
from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID


def test_chatgpt_profile_disables_only_native_tool_search() -> None:
    default = {
        "supports_tools": True,
        "supported_native_tools": frozenset({ToolSearchTool, WebSearchTool}),
    }

    profile = model_factory._chatgpt_model_profile(default)

    assert profile["supports_tools"] is True
    assert profile["supported_native_tools"] == frozenset({WebSearchTool})
    assert default["supported_native_tools"] == frozenset(
        {ToolSearchTool, WebSearchTool}
    )


def test_chatgpt_request_rewrite_preserves_transport_metadata() -> None:
    request = httpx.Request(
        "POST",
        "https://chatgpt.com/backend-api/codex/responses",
        json={
            "instructions": "",
            "max_output_tokens": 100,
            "prompt_cache_key": "cache",
        },
        extensions={"timeout": {"connect": 10.0}},
    )

    rewritten = model_factory._rewrite_chatgpt_request(request, "default instructions")
    body = json.loads(rewritten.content)

    assert body["instructions"] == "default instructions"
    assert body["store"] is False
    assert body["stream"] is True
    assert "max_output_tokens" not in body
    assert "prompt_cache_key" not in body
    assert rewritten.headers["accept"] == "text/event-stream"
    assert rewritten.extensions == request.extensions


async def test_chatgpt_http_client_keeps_default_transport() -> None:
    client = model_factory._ChatGPTHTTPClient("default instructions")
    try:
        assert type(client._transport) is httpx.AsyncHTTPTransport
        request = httpx.Request(
            "POST",
            "https://chatgpt.com/backend-api/codex/responses",
            json={},
        )
        response = httpx.Response(200, request=request)
        with patch.object(
            httpx.AsyncClient,
            "send",
            new=AsyncMock(return_value=response),
        ) as send:
            await client.send(request)

        rewritten = send.await_args.args[0]
        assert json.loads(rewritten.content)["stream"] is True
    finally:
        await client.aclose()


def test_openai_handler_uses_v2_chat_model() -> None:
    model = model_factory._create_openai_model(
        "gpt-4o",
        "test-key",
        PROVIDER_REGISTRY_BY_ID["openai"],
    )

    assert isinstance(model, OpenAIChatModel)


def test_ollama_handler_uses_v2_chat_model() -> None:
    model = model_factory._create_ollama_model(
        "qwen3",
        "",
        PROVIDER_REGISTRY_BY_ID["ollama"],
    )

    assert isinstance(model, OpenAIChatModel)


def test_native_openai_compatible_provider_uses_v2_chat_model() -> None:
    model = model_factory._create_via_native_provider(
        "deepseek-chat",
        "test-key",
        PROVIDER_REGISTRY_BY_ID["deepseek"],
    )

    assert isinstance(model, OpenAIChatModel)


def test_litellm_proxy_handler_uses_v2_chat_model(monkeypatch) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    model = model_factory._create_litellm_proxy_model(
        "proxy-model",
        "",
        PROVIDER_REGISTRY_BY_ID["litellm_proxy"],
    )

    assert isinstance(model, OpenAIChatModel)


def test_thinking_settings_default_to_the_model_default() -> None:
    assert model_factory.build_thinking_settings(None) == {}
    assert model_factory.build_thinking_settings("auto") == {}
    assert model_factory.build_thinking_settings("  ") == {}


def test_thinking_settings_apply_effort_and_shadow_gemini_native_config() -> None:
    settings = model_factory.build_thinking_settings("high")

    assert settings["thinking"] == "high"
    # config/providers.json sets google_thinking_config for Gemini, and a native
    # config outranks the unified setting unless it is blanked out.
    assert settings["google_thinking_config"] == {}


def test_thinking_settings_can_switch_thinking_off() -> None:
    assert model_factory.build_thinking_settings("off")["thinking"] is False


def test_unknown_thinking_value_falls_back_to_the_model_default() -> None:
    assert model_factory.build_thinking_settings("turbo") == {}


def test_local_server_thinking_uses_the_chat_template_switch() -> None:
    # SGLang/vLLM models resolve to the plain OpenAI profile, so the unified
    # setting alone is dropped and the served model keeps thinking.
    off = model_factory.build_thinking_settings("off", "sglang")
    assert off["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    on = model_factory.build_thinking_settings("high", "vllm")
    assert on["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}


def test_hosted_providers_get_no_chat_template_switch() -> None:
    assert "extra_body" not in model_factory.build_thinking_settings("off", "anthropic")


def test_local_server_thinking_left_on_auto_sends_nothing() -> None:
    assert model_factory.build_thinking_settings("auto", "sglang") == {}


def _history_with_chat_completions_thinking():
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ThinkingPart,
        UserPromptPart,
    )

    return [
        ModelRequest(parts=[UserPromptPart(content="news please")]),
        ModelResponse(
            parts=[
                ThinkingPart(
                    content="plan the search",
                    id="reasoning_content",
                    provider_name="openai",
                ),
                TextPart(content="done"),
            ],
            provider_name="openai",
        ),
        ModelResponse(
            parts=[
                ThinkingPart(content="native", id="rs_abc", provider_name="openai"),
                TextPart(content="ok"),
            ],
            provider_name="openai",
        ),
        ModelRequest(parts=[UserPromptPart(content="again")]),
    ]


def test_drop_foreign_reasoning_ids_keeps_native_reasoning() -> None:
    history = _history_with_chat_completions_thinking()

    cleaned = model_factory.drop_foreign_reasoning_ids(history)

    assert cleaned[1].parts[0].id is None
    assert cleaned[1].parts[0].content == "plan the search"
    assert cleaned[2].parts[0].id == "rs_abc"
    assert cleaned[2] is history[2]
    assert history[1].parts[0].id == "reasoning_content"


async def test_responses_replay_sends_no_non_rs_reasoning_item() -> None:
    from openai import AsyncOpenAI
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    model = OpenAIResponsesModel(
        "gpt-5",
        provider=OpenAIProvider(openai_client=AsyncOpenAI(api_key="test")),
    )
    history = model_factory.drop_foreign_reasoning_ids(
        _history_with_chat_completions_thinking()
    )

    _, items = await model._map_messages(history, {}, ModelRequestParameters())

    reasoning_ids = [i["id"] for i in items if i.get("type") == "reasoning"]
    assert all(rid.startswith("rs_") for rid in reasoning_ids)
    assert any("plan the search" in str(i.get("content")) for i in items)
