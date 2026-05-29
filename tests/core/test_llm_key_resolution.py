import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from suzent.core.providers.catalog import ProviderSpec
from suzent import llm
from suzent.llm import EmbeddingGenerator, LLMClient


def test_llm_client_passes_resolved_provider_key_to_litellm(monkeypatch):
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "gemini" else None,
    )
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(LLMClient(model="gemini/gemini-2.5-flash").complete("hello"))

    assert result == "ok"
    fake_litellm.acompletion.assert_awaited_once()
    assert fake_litellm.acompletion.await_args.kwargs["api_key"] == "synced-key"


def test_embedding_generator_passes_resolved_provider_key_to_litellm(
    monkeypatch,
):
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "gemini" else None,
    )
    fake_litellm = SimpleNamespace(aembedding=AsyncMock())
    fake_litellm.aembedding.return_value = SimpleNamespace(
        data=[{"embedding": [0.1, 0.2]}]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        EmbeddingGenerator(model="gemini/gemini-embedding-001", dimension=2).generate(
            "hello"
        )
    )

    assert result == [0.1, 0.2]
    fake_litellm.aembedding.assert_awaited_once()
    assert fake_litellm.aembedding.await_args.kwargs["api_key"] == "synced-key"


def test_litellm_client_omits_api_key_when_provider_key_is_unset(monkeypatch):
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(LLMClient(model="unknown/model").complete("hello"))

    assert "api_key" not in fake_litellm.acompletion.await_args.kwargs


def test_litellm_client_routes_openai_compat_provider_to_openai_base(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "xiaomi_mimo" else None,
    )
    monkeypatch.setitem(
        llm.PROVIDER_REGISTRY_BY_ID,
        "xiaomi_mimo",
        ProviderSpec(
            id="xiaomi_mimo",
            label="Xiaomi MiMo",
            api_type="openai",
            env_keys=["XIAOMI_MIMO_API_KEY"],
            base_url="https://api.xiaomimimo.com/v1",
        ),
    )
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(LLMClient(model="xiaomi_mimo/mimo-v2.5-omni").complete("hello"))

    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert fake_litellm.acompletion.await_args.kwargs["model"] == (
        "openai/mimo-v2.5-omni"
    )
    assert kwargs["api_key"] == "synced-key"
    assert kwargs["api_base"] == "https://api.xiaomimimo.com/v1"


def test_litellm_client_uses_configured_provider_base_url(monkeypatch) -> None:
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "xiaomi_mimo" else None,
    )
    monkeypatch.setitem(
        llm.PROVIDER_REGISTRY_BY_ID,
        "xiaomi_mimo",
        ProviderSpec(
            id="xiaomi_mimo",
            label="Xiaomi MiMo",
            api_type="openai",
            env_keys=["XIAOMI_MIMO_API_KEY"],
            fields=[
                {
                    "key": "XIAOMI_MIMO_BASE_URL",
                    "label": "Base URL",
                    "placeholder": "",
                    "type": "text",
                }
            ],
            base_url="https://api.xiaomimimo.com/v1",
        ),
    )

    class _SecretManager:
        def get(self, key: str) -> str | None:
            if key == "XIAOMI_MIMO_BASE_URL":
                return "https://custom.example.test/v1"
            return None

    monkeypatch.setattr(
        "suzent.core.secrets.get_secret_manager", lambda: _SecretManager()
    )
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(LLMClient(model="xiaomi_mimo/mimo-v2.5-omni").complete("hello"))

    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert kwargs["model"] == "openai/mimo-v2.5-omni"
    assert kwargs["api_base"] == "https://custom.example.test/v1"
