"""
Model factory for pydantic-ai.

Maps LiteLLM-style model IDs (used throughout suzent's config and DB)
to pydantic-ai model objects.

Strategy:
- Native pydantic-ai model classes  → GoogleModel, AnthropicModel, XaiModel, OpenRouterModel
- Native OpenAI-compat providers    → OpenAIModel + provider-specific class (see _NATIVE_OPENAI_COMPAT)
- LiteLLM Proxy (litellm_proxy/)   → OpenAIModel + LiteLLMProvider
- Other OpenAI-compat (COMPAT dict) → OpenAIModel + OpenAIProvider(base_url)
- Truly unknown prefix              → raise a clear RuntimeError
"""

from __future__ import annotations

import os

from suzent.core.providers.catalog import OPENAI_COMPAT_PROVIDERS
from suzent.core.providers.helpers import resolve_api_key
from suzent.logger import get_logger

logger = get_logger(__name__)

# Providers that wrap OpenAIModel with a native pydantic-ai provider class.
# Checked before OPENAI_COMPAT_PROVIDERS so these use the proper integration.
# Format: prefix → (module_path, ProviderClass name)
_NATIVE_OPENAI_COMPAT: dict[str, tuple[str, str]] = {
    "deepseek": ("pydantic_ai.providers.deepseek", "DeepSeekProvider"),
    "moonshot": ("pydantic_ai.providers.moonshotai", "MoonshotAIProvider"),
    "together": ("pydantic_ai.providers.together", "TogetherProvider"),
    "fireworks": ("pydantic_ai.providers.fireworks", "FireworksProvider"),
    "sambanova": ("pydantic_ai.providers.sambanova", "SambaNovaProvider"),
}


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

    # --- Google / Gemini ---
    if prefix in ("gemini", "google"):
        api_key = resolve_api_key("gemini")
        if api_key:
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider
            from pydantic_ai.settings import ModelSettings

            settings = ModelSettings(google_thinking_config={"include_thoughts": True})
            logger.debug(f"Mapped {model_id} → GoogleModel({model_name})")
            return GoogleModel(
                model_name, provider=GoogleProvider(api_key=api_key), settings=settings
            )
        logger.warning(f"No API key for Gemini; cannot load {model_id}")

    # --- Anthropic ---
    elif prefix == "anthropic":
        api_key = resolve_api_key("anthropic")
        if api_key:
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            logger.debug(f"Mapped {model_id} → AnthropicModel({model_name})")
            return AnthropicModel(
                model_name, provider=AnthropicProvider(api_key=api_key)
            )
        logger.warning(f"No API key for Anthropic; cannot load {model_id}")

    # --- xAI (Grok) ---
    elif prefix == "xai":
        api_key = resolve_api_key("xai")
        if api_key:
            from pydantic_ai.models.xai import XaiModel
            from pydantic_ai.providers.xai import XaiProvider

            logger.debug(f"Mapped {model_id} → XaiModel({model_name})")
            return XaiModel(model_name, provider=XaiProvider(api_key=api_key))
        logger.warning(f"No API key for xAI; cannot load {model_id}")

    # --- OpenRouter ---
    elif prefix == "openrouter":
        api_key = resolve_api_key("openrouter")
        if api_key:
            from pydantic_ai.models.openrouter import OpenRouterModel
            from pydantic_ai.providers.openrouter import OpenRouterProvider

            logger.debug(f"Mapped {model_id} → OpenRouterModel({model_name})")
            return OpenRouterModel(
                model_name, provider=OpenRouterProvider(api_key=api_key)
            )
        logger.warning(f"No API key for OpenRouter; cannot load {model_id}")

    # --- OpenAI ---
    elif prefix == "openai":
        api_key = resolve_api_key("openai")
        if api_key:
            from pydantic_ai.models.openai import OpenAIModel
            from pydantic_ai.providers.openai import OpenAIProvider

            base_url = os.environ.get("OPENAI_BASE_URL")
            logger.debug(f"Mapped {model_id} → OpenAIModel({model_name})")
            return OpenAIModel(
                model_name, provider=OpenAIProvider(api_key=api_key, base_url=base_url)
            )
        logger.warning(f"No API key for OpenAI; cannot load {model_id}")

    # --- Ollama (local, no auth) ---
    elif prefix == "ollama":
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.ollama import OllamaProvider

        base_url = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        logger.debug(
            f"Mapped {model_id} → OpenAIModel via OllamaProvider({model_name})"
        )
        return OpenAIModel(model_name, provider=OllamaProvider(base_url=base_url))

    # --- LiteLLM Proxy ---
    elif prefix == "litellm_proxy":
        base_url = os.environ.get("LITELLM_BASE_URL") or os.environ.get(
            "LITELLM_PROXY_API_BASE"
        )
        if base_url:
            from pydantic_ai.models.openai import OpenAIModel
            from pydantic_ai.providers.litellm import LiteLLMProvider

            api_key = (
                os.environ.get("LITELLM_MASTER_KEY")
                or os.environ.get("LITELLM_PROXY_API_KEY")
                or "sk-1234"
            )
            logger.debug(
                f"Mapped {model_id} → OpenAIModel via LiteLLMProvider({model_name})"
            )
            return OpenAIModel(
                model_name, provider=LiteLLMProvider(api_key=api_key, api_base=base_url)
            )
        logger.warning(f"LITELLM_BASE_URL not set; cannot load {model_id}")

    # --- Providers with native pydantic-ai OpenAI-compat wrappers ---
    elif prefix in _NATIVE_OPENAI_COMPAT:
        api_key = resolve_api_key(prefix)
        if api_key:
            import importlib

            from pydantic_ai.models.openai import OpenAIModel

            module_path, class_name = _NATIVE_OPENAI_COMPAT[prefix]
            ProviderClass = getattr(importlib.import_module(module_path), class_name)
            logger.debug(
                f"Mapped {model_id} → OpenAIModel via {class_name}({model_name})"
            )
            return OpenAIModel(model_name, provider=ProviderClass(api_key=api_key))
        logger.warning(f"No API key for {prefix}; cannot load {model_id}")

    # --- Remaining OpenAI-compatible providers (hardcoded base URLs) ---
    elif prefix in OPENAI_COMPAT_PROVIDERS:
        api_key = resolve_api_key(prefix)
        if api_key:
            from pydantic_ai.models.openai import OpenAIModel
            from pydantic_ai.providers.openai import OpenAIProvider

            logger.debug(
                f"Mapped {model_id} → OpenAIModel via {prefix} compat API({model_name})"
            )
            return OpenAIModel(
                model_name,
                provider=OpenAIProvider(
                    api_key=api_key, base_url=OPENAI_COMPAT_PROVIDERS[prefix]
                ),
            )
        logger.warning(f"No API key for {prefix}; cannot load {model_id}")

    else:
        raise RuntimeError(
            f"Unknown model provider '{prefix}' in model ID '{model_id}'. "
            f"Add it to OPENAI_COMPAT_PROVIDERS in catalog.py if it uses an OpenAI-compatible API, "
            f"or add a native pydantic-ai mapping in model_factory.py."
        )

    # Reached only when a known provider has no API key configured
    raise RuntimeError(
        f"No API key configured for model '{model_id}'. "
        f"Add your credentials in Settings → Providers."
    )
