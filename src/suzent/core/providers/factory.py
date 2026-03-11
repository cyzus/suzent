from __future__ import annotations

from typing import Any, Dict

from suzent.core.providers.base import BaseProvider
from suzent.core.providers.catalog import OPENAI_COMPAT_PROVIDERS
from suzent.core.providers.generic import GenericLiteLLMProvider
from suzent.core.providers.litellm_proxy import LiteLLMProxyProvider
from suzent.core.providers.ollama import OllamaProvider
from suzent.core.providers.openai import OpenAIProvider
from suzent.core.providers.openai_compat import OpenAICompatProvider


class ProviderFactory:
    # Providers with fully custom discovery logic.
    _registry: Dict[str, type] = {
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "litellm_proxy": LiteLLMProxyProvider,
    }

    @classmethod
    def get_provider(cls, provider_id: str, config: Dict[str, Any]) -> BaseProvider:
        if provider_id in cls._registry:
            return cls._registry[provider_id](provider_id, config)

        # OpenAI-compatible providers: query /v1/models directly
        if provider_id in OPENAI_COMPAT_PROVIDERS:
            return OpenAICompatProvider(
                provider_id, config, OPENAI_COMPAT_PROVIDERS[provider_id]
            )

        # Everything else: try LiteLLM's get_valid_models (covers Anthropic, Gemini, Groq, Mistral, etc.)
        return GenericLiteLLMProvider(provider_id, config)
