"""Provider package for Suzent."""

from suzent.core.providers.base import BaseProvider, Model, _temporary_env, prefixed
from suzent.core.providers.catalog import (
    OPENAI_COMPAT_PROVIDERS,
    PROVIDER_CONFIG,
    PROVIDER_CONFIG_BY_ID,
    PROVIDER_ENV_KEYS,
)
from suzent.core.providers.factory import ProviderFactory
from suzent.core.providers.generic import GenericLiteLLMProvider
from suzent.core.providers.helpers import (
    get_effective_memory_config,
    get_enabled_models_from_db,
    resolve_api_key,
)
from suzent.core.providers.litellm_proxy import LiteLLMProxyProvider
from suzent.core.providers.ollama import OllamaProvider
from suzent.core.providers.openai import OpenAIProvider
from suzent.core.providers.openai_compat import OpenAICompatProvider

__all__ = [
    # base
    "BaseProvider",
    "Model",
    "_temporary_env",
    "prefixed",
    # catalog
    "PROVIDER_CONFIG",
    "PROVIDER_CONFIG_BY_ID",
    "PROVIDER_ENV_KEYS",
    "OPENAI_COMPAT_PROVIDERS",
    # implementations
    "OpenAIProvider",
    "OllamaProvider",
    "LiteLLMProxyProvider",
    "GenericLiteLLMProvider",
    "OpenAICompatProvider",
    # factory & helpers
    "ProviderFactory",
    "resolve_api_key",
    "get_enabled_models_from_db",
    "get_effective_memory_config",
]
