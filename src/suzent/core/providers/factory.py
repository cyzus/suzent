from __future__ import annotations

from typing import Any, Dict

from suzent.core.providers.base import BaseProvider
from suzent.core.providers.catalog import OPENAI_COMPAT_PROVIDERS
from suzent.core.providers.generic import GenericLiteLLMProvider
from suzent.core.providers.litellm_proxy import LiteLLMProxyProvider
from suzent.core.providers.ollama import OllamaProvider
from suzent.core.providers.chatgpt import ChatGPTProvider
from suzent.core.providers.openai import OpenAIProvider
from suzent.core.providers.openai_compat import OpenAICompatProvider


class ProviderFactory:
    # Providers with fully custom discovery logic.
    _registry: Dict[str, type] = {
        "openai": OpenAIProvider,
        "chatgpt": ChatGPTProvider,
        "ollama": OllamaProvider,
        "litellm_proxy": LiteLLMProxyProvider,
    }

    @classmethod
    def get_provider(cls, provider_id: str, config: Dict[str, Any]) -> BaseProvider:
        if provider_id in cls._registry:
            return cls._registry[provider_id](provider_id, config)

        # OpenAI-compatible providers: query /v1/models directly
        if provider_id in OPENAI_COMPAT_PROVIDERS:
            # Allow user config to override the catalog base_url
            user_base_url = None
            if config:
                # Find the env key for base url
                from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID

                spec = PROVIDER_REGISTRY_BY_ID.get(provider_id)
                if spec:
                    for field in spec.fields:
                        if "BASE_URL" in field["key"]:
                            user_base_url = config.get(field["key"])
                            break

            base_url = user_base_url or OPENAI_COMPAT_PROVIDERS[provider_id]
            return OpenAICompatProvider(provider_id, config, base_url)

        # Everything else: try LiteLLM's get_valid_models (covers Anthropic, Gemini, Groq, Mistral, etc.)
        return GenericLiteLLMProvider(provider_id, config)
