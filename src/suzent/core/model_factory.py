"""
Model factory for pydantic-ai — registry-driven dispatch.

Maps LiteLLM-style model IDs (``provider/model-name``) to pydantic-ai model
objects.  Routing is determined by the provider's ``api_type`` from the
provider registry (``config/providers.json``), eliminating hardcoded
``elif`` chains.

Dispatch strategy (in priority order):
    1. **Dedicated handlers** — providers with unique pydantic-ai integration
       (``google``, ``xai``, ``openrouter``, ``ollama``, ``litellm_proxy``).
    2. **Native pydantic-ai provider class** — ``native_provider`` field in
       the registry (e.g. DeepSeekProvider, MoonshotAIProvider).
    3. **Compat routing** — ``api_type`` + ``base_url`` from the registry
       (OpenAI-compat or Anthropic-compat third parties).
    4. **Direct api_type match** — providers that share a protocol with a
       first-party provider (e.g. ``api_type: "openai"`` without base_url
       uses the standard OpenAI endpoint).
"""

from __future__ import annotations

import importlib
import os
from typing import Any

from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID, ProviderSpec
from suzent.core.providers.helpers import resolve_api_key
from suzent.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# API-type handler registry
# ---------------------------------------------------------------------------
# Maps api_type → callable(model_name, api_key, spec) → pydantic-ai Model.
# Each handler lazily imports the pydantic-ai classes it needs.


def _create_openai_model(model_name: str, api_key: str, spec: ProviderSpec) -> object:
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    base_url = spec.base_url or os.environ.get("OPENAI_BASE_URL")
    return OpenAIModel(
        model_name, provider=OpenAIProvider(api_key=api_key, base_url=base_url)
    )


def _create_anthropic_model(
    model_name: str, api_key: str, spec: ProviderSpec
) -> object:
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    kwargs: dict[str, Any] = {"api_key": api_key}
    if spec.base_url:
        kwargs["base_url"] = spec.base_url
    return AnthropicModel(model_name, provider=AnthropicProvider(**kwargs))


def _create_google_model(model_name: str, api_key: str, spec: ProviderSpec) -> object:
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider
    from pydantic_ai.settings import ModelSettings

    settings_kwargs = spec.model_settings or {
        "google_thinking_config": {"include_thoughts": True}
    }
    settings = ModelSettings(**settings_kwargs)
    return GoogleModel(
        model_name, provider=GoogleProvider(api_key=api_key), settings=settings
    )


def _create_xai_model(model_name: str, api_key: str, spec: ProviderSpec) -> object:
    from pydantic_ai.models.xai import XaiModel
    from pydantic_ai.providers.xai import XaiProvider

    return XaiModel(model_name, provider=XaiProvider(api_key=api_key))


def _create_openrouter_model(
    model_name: str, api_key: str, spec: ProviderSpec
) -> object:
    from pydantic_ai.models.openrouter import OpenRouterModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    return OpenRouterModel(model_name, provider=OpenRouterProvider(api_key=api_key))


def _create_ollama_model(model_name: str, _api_key: str, spec: ProviderSpec) -> object:
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.ollama import OllamaProvider

    base_url = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
    return OpenAIModel(model_name, provider=OllamaProvider(base_url=base_url))


def _create_litellm_proxy_model(
    model_name: str, _api_key: str, spec: ProviderSpec
) -> object:
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.litellm import LiteLLMProvider

    base_url = os.environ.get("LITELLM_BASE_URL") or os.environ.get(
        "LITELLM_PROXY_API_BASE"
    )
    if not base_url:
        raise RuntimeError(
            "LITELLM_BASE_URL not set; cannot load litellm_proxy models. "
            "Configure it in Settings → Providers."
        )
    api_key = (
        os.environ.get("LITELLM_MASTER_KEY")
        or os.environ.get("LITELLM_PROXY_API_KEY")
        or "sk-1234"
    )
    return OpenAIModel(
        model_name, provider=LiteLLMProvider(api_key=api_key, api_base=base_url)
    )


# Maps api_type → handler function
_API_TYPE_HANDLERS: dict[str, Any] = {
    "openai": _create_openai_model,
    "anthropic": _create_anthropic_model,
    "google": _create_google_model,
    "xai": _create_xai_model,
    "openrouter": _create_openrouter_model,
    "ollama": _create_ollama_model,
    "litellm_proxy": _create_litellm_proxy_model,
}


# ---------------------------------------------------------------------------
# Native provider helper
# ---------------------------------------------------------------------------


def _create_via_native_provider(
    model_name: str, api_key: str, spec: ProviderSpec
) -> object:
    """Create a model using the provider's native pydantic-ai provider class."""
    from pydantic_ai.models.openai import OpenAIModel

    native = spec.native_provider
    assert native is not None
    module = importlib.import_module(native["module"])
    provider_cls = getattr(module, native["class"])
    return OpenAIModel(model_name, provider=provider_cls(api_key=api_key))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_pydantic_ai_model(model_id: str) -> object:
    """Create a pydantic-ai model reference from a LiteLLM-style model ID.

    Args:
        model_id: LiteLLM-style model identifier, e.g.
            ``"openai/gpt-4.1"``, ``"gemini/gemini-2.5-pro"``,
            ``"deepseek/deepseek-chat"``, ``"litellm_proxy/my-model"``.
    """
    prefix, _, model_name = model_id.partition("/")
    if not model_name:
        model_name = model_id

    spec = PROVIDER_REGISTRY_BY_ID.get(prefix)
    if spec is None:
        raise RuntimeError(
            f"Unknown model provider '{prefix}' in model ID '{model_id}'. "
            f"Register it in config/providers.json (or config/providers.user.json "
            f"for custom providers)."
        )

    # Resolve API key (ollama / litellm_proxy may not require one)
    api_key = resolve_api_key(prefix)
    requires_key = spec.api_type not in ("ollama",)

    if requires_key and not api_key:
        raise RuntimeError(
            f"No API key configured for model '{model_id}'. "
            f"Add your credentials in Settings → Providers."
        )

    # Dispatch: native provider class takes priority over base_url compat
    if spec.has_native_provider:
        logger.debug(
            "Mapped %s → OpenAIModel via %s",
            model_id,
            spec.native_provider["class"],
        )
        return _create_via_native_provider(model_name, api_key or "", spec)

    handler = _API_TYPE_HANDLERS.get(spec.api_type)
    if handler is None:
        raise RuntimeError(
            f"Unsupported api_type '{spec.api_type}' for provider '{prefix}'. "
            f"Supported types: {', '.join(sorted(_API_TYPE_HANDLERS))}."
        )

    logger.debug(
        "Mapped %s → %s (api_type=%s, base_url=%s)",
        model_id,
        handler.__name__,
        spec.api_type,
        spec.base_url,
    )
    return handler(model_name, api_key or "", spec)


def create_fallback_model(model_ids: list[str]) -> object:
    """Create a FallbackModel from multiple model IDs.

    If only one model ID is provided, returns a single model (no wrapping).

    Args:
        model_ids: List of LiteLLM-style model identifiers.
    """
    if not model_ids:
        raise ValueError("At least one model ID is required for fallback.")

    models = [create_pydantic_ai_model(mid) for mid in model_ids]
    if len(models) == 1:
        return models[0]

    from pydantic_ai.models.fallback import FallbackModel

    return FallbackModel(*models)
