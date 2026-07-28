import json
from unittest.mock import AsyncMock, patch

import httpx
from pydantic_ai.models.openai import OpenAIChatModel

from suzent.core import model_factory
from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID


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
