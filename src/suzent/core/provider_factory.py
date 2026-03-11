"""
Backwards-compatibility shim.

All provider logic has moved to suzent.core.providers/.
This module re-exports everything so existing imports keep working.
"""

from suzent.core.providers import (  # noqa: F401
    BaseProvider,
    GenericLiteLLMProvider,
    LiteLLMProxyProvider,
    Model,
    PROVIDER_CONFIG,
    PROVIDER_ENV_KEYS,
    ProviderFactory,
    _temporary_env,
    get_effective_memory_config,
    get_enabled_models_from_db,
    OllamaProvider,
    OpenAIProvider,
    resolve_api_key,
)

# Legacy alias
LiteLLMProvider = LiteLLMProxyProvider
