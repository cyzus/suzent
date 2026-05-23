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
            # Allow user config or SecretManager to override the catalog base_url
            user_base_url = None

            from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID

            spec = PROVIDER_REGISTRY_BY_ID.get(provider_id)
            if spec:
                for field in spec.fields:
                    if "BASE_URL" in field["key"]:
                        env_key = field["key"]
                        # 1. Check explicit dict
                        if config and env_key in config:
                            user_base_url = config[env_key]
                            break
                        # 2. Check SecretManager (where API keys / URLs from frontend are saved)
                        try:
                            from suzent.core.secrets import get_secret_manager

                            sm = get_secret_manager()
                            val = sm.get(env_key)
                            if val:
                                user_base_url = val
                                break
                        except Exception:
                            pass
                        # 3. Check OS env
                        import os

                        val = os.environ.get(env_key)
                        if val:
                            user_base_url = val
                            break

            base_url = user_base_url or OPENAI_COMPAT_PROVIDERS[provider_id]
            return OpenAICompatProvider(provider_id, config, base_url)

        # Everything else: try LiteLLM's get_valid_models (covers Anthropic, Gemini, Groq, Mistral, etc.)
        return GenericLiteLLMProvider(provider_id, config)
