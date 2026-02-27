"""
Model factory for pydantic-ai.

Maps LiteLLM-style model IDs (used throughout suzent's config and DB)
to pydantic-ai model objects.  For natively supported providers we use
pydantic-ai's built-in provider objects; for everything else we fall
back to LiteLLMModel which delegates to the litellm library.
"""

from __future__ import annotations

import os
from typing import Union

from suzent.logger import get_logger

logger = get_logger(__name__)

# Env var names used by suzent's DB / provider_factory for each provider.
# pydantic-ai may expect different names (e.g. GOOGLE_API_KEY vs GEMINI_API_KEY),
# so we resolve keys explicitly when constructing provider objects.
_PROVIDER_ENV_KEYS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "groq": ["GROQ_API_KEY"],
}

# Providers that should use OpenAI-compatible endpoint via LiteLLM.
_LITELLM_PROVIDERS: set[str] = {
    "deepseek/",
    "ollama/",
    "together/",
}


def _resolve_api_key(provider: str) -> str | None:
    """Look up the API key for a provider from environment variables."""
    for env_key in _PROVIDER_ENV_KEYS.get(provider, []):
        val = os.environ.get(env_key)
        if val:
            return val
    return None


def create_pydantic_ai_model(model_id: str) -> Union[str, object]:
    """Create a pydantic-ai model reference from a LiteLLM-style model ID.

    Returns either:
    - A pydantic-ai ``Model`` instance with explicitly resolved API key, **or**
    - A ``LiteLLMModel`` instance for everything else.

    Args:
        model_id: LiteLLM-style model identifier, e.g.
            ``"openai/gpt-4.1"``, ``"gemini/gemini-2.5-pro"``,
            ``"deepseek/deepseek-chat"``.
    """

    # --- Google / Gemini ---
    if model_id.startswith(("gemini/", "google/")):
        model_name = model_id.split("/", 1)[1]
        api_key = _resolve_api_key("gemini")
        logger.info(
            f"Google model resolve: model_id={model_id}, "
            f"GEMINI_API_KEY={'set' if os.environ.get('GEMINI_API_KEY') else 'missing'}, "
            f"GOOGLE_API_KEY={'set' if os.environ.get('GOOGLE_API_KEY') else 'missing'}, "
            f"resolved={'yes' if api_key else 'no'}"
        )
        if api_key:
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider

            provider = GoogleProvider(api_key=api_key)
            logger.debug(f"Mapped {model_id} → GoogleModel({model_name})")
            return GoogleModel(model_name, provider=provider)
        # Fall through to LiteLLM if no key found
        logger.warning(f"No API key for Gemini; falling back to LiteLLM for {model_id}")

    # --- OpenAI ---
    elif model_id.startswith("openai/"):
        model_name = model_id.split("/", 1)[1]
        api_key = _resolve_api_key("openai")
        base_url = os.environ.get("OPENAI_BASE_URL")
        if api_key:
            from pydantic_ai.models.openai import OpenAIModel
            from pydantic_ai.providers.openai import OpenAIProvider

            provider = OpenAIProvider(api_key=api_key, base_url=base_url)
            logger.debug(f"Mapped {model_id} → OpenAIModel({model_name})")
            return OpenAIModel(model_name, provider=provider)
        logger.warning(f"No API key for OpenAI; falling back to LiteLLM for {model_id}")

    # --- Anthropic ---
    elif model_id.startswith("anthropic/"):
        model_name = model_id.split("/", 1)[1]
        api_key = _resolve_api_key("anthropic")
        if api_key:
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            provider = AnthropicProvider(api_key=api_key)
            logger.debug(f"Mapped {model_id} → AnthropicModel({model_name})")
            return AnthropicModel(model_name, provider=provider)
        logger.warning(f"No API key for Anthropic; falling back to LiteLLM for {model_id}")

    # --- Groq ---
    elif model_id.startswith("groq/"):
        model_name = model_id.split("/", 1)[1]
        api_key = _resolve_api_key("groq")
        if api_key:
            from pydantic_ai.models.groq import GroqModel
            from pydantic_ai.providers.groq import GroqProvider

            provider = GroqProvider(api_key=api_key)
            logger.debug(f"Mapped {model_id} → GroqModel({model_name})")
            return GroqModel(model_name, provider=provider)
        logger.warning(f"No API key for Groq; falling back to LiteLLM for {model_id}")

    # --- Fall back to LiteLLMModel for all other providers ---
    try:
        from pydantic_ai.models.litellm import LiteLLMModel

        logger.debug(f"Using LiteLLMModel for: {model_id}")
        return LiteLLMModel(model_id)
    except ImportError:
        logger.warning(
            "pydantic-ai litellm extra not installed; "
            "falling back to raw model ID string"
        )
        return model_id
