from pydantic_ai.models.openai import OpenAIChatModel

from suzent.core import model_factory
from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID


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
