import asyncio
import json
import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import List, Optional, Dict, Any

import aiohttp
from pydantic import BaseModel

from suzent.config import CONFIG
from suzent.logger import get_logger


logger = get_logger(__name__)


@contextmanager
def _temporary_env(key: str, value: str):
    """
    Context manager to temporarily set an environment variable, restoring
    the original value (or removing it) on exit.
    """
    original = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


# Provider Configuration Definition
PROVIDER_CONFIG = [
    {
        "id": "openai",
        "label": "OpenAI",
        "default_models": [
            {"id": "openai/gpt-4.1", "name": "GPT-4.1"},
            {"id": "openai/gpt-5-mini", "name": "GPT-5 Mini"},
            {"id": "openai/gpt-5.1", "name": "GPT-5.1"},
        ],
        "fields": [
            {
                "key": "OPENAI_API_KEY",
                "label": "API Key",
                "placeholder": "sk-...",
                "type": "secret",
            },
            {
                "key": "OPENAI_BASE_URL",
                "label": "Base URL (Optional)",
                "placeholder": "https://api.openai.com/v1",
                "type": "text",
            },
        ],
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "default_models": [],
        "fields": [
            {
                "key": "ANTHROPIC_API_KEY",
                "label": "API Key",
                "placeholder": "sk-ant-...",
                "type": "secret",
            }
        ],
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "default_models": [
            {"id": "gemini/gemini-3-pro-preview", "name": "Gemini 3 Pro Preview"},
            {"id": "gemini/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
            {"id": "gemini/gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
        ],
        "fields": [
            {
                "key": "GEMINI_API_KEY",
                "label": "API Key",
                "placeholder": "AIza...",
                "type": "secret",
            }
        ],
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "default_models": [{"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat"}],
        "fields": [
            {
                "key": "DEEPSEEK_API_KEY",
                "label": "API Key",
                "placeholder": "sk-...",
                "type": "secret",
            },
            {
                "key": "DEEPSEEK_API_BASE",
                "label": "Base URL (Optional)",
                "placeholder": "https://api.deepseek.com",
                "type": "text",
            },
        ],
    },
    {
        "id": "litellm",
        "label": "LiteLLM Proxy",
        "default_models": [],  # Dynamic
        "fields": [
            {
                "key": "LITELLM_MASTER_KEY",
                "label": "Master Key",
                "placeholder": "sk-...",
                "type": "secret",
            },
            {
                "key": "LITELLM_BASE_URL",
                "label": "Base URL",
                "placeholder": "http://localhost:4000",
                "type": "text",
            },
        ],
    },
    {
        "id": "ollama",
        "label": "Ollama",
        "default_models": [],  # Dynamic
        "fields": [
            {
                "key": "OLLAMA_BASE_URL",
                "label": "Base URL",
                "placeholder": "http://localhost:11434",
                "type": "text",
            },
            {
                "key": "OLLAMA_API_KEY",
                "label": "API Key (Optional)",
                "placeholder": "...",
                "type": "secret",
            },
        ],
    },
]


def get_enabled_models_from_db() -> List[str]:
    """Aggregate all enabled/available models from provider config stored in the database."""
    from suzent.database import get_database

    db = get_database()
    api_keys = db.get_api_keys() or {}
    provider_config_blob = api_keys.get("_PROVIDER_CONFIG_")

    custom_config = {}
    if provider_config_blob:
        try:
            custom_config = json.loads(provider_config_blob)
        except json.JSONDecodeError:
            pass

    if not custom_config:
        if CONFIG.model_options:
            return CONFIG.model_options

        # Fallback to built-in defaults from PROVIDER_CONFIG
        defaults = [
            m["id"] for p in PROVIDER_CONFIG for m in p.get("default_models", [])
        ]
        return sorted(set(defaults))

    # Collect all user-enabled models across providers
    all_models = [
        model_id
        for p in PROVIDER_CONFIG
        for model_id in custom_config.get(p["id"], {}).get("enabled_models", [])
    ]

    return sorted(set(all_models))


def get_effective_memory_config() -> Dict[str, str]:
    """
    Get the effective memory configuration, preferring user settings from DB
    and falling back to global CONFIG defaults.

    Returns:
        Dict with keys 'embedding_model' and 'extraction_model'.
    """
    from suzent.database import get_database

    try:
        db = get_database()
        memory_config = db.get_memory_config()

        embedding_model = (
            memory_config.embedding_model
            if memory_config and memory_config.embedding_model
            else CONFIG.embedding_model
        )
        extraction_model = (
            memory_config.extraction_model
            if memory_config and memory_config.extraction_model
            else CONFIG.extraction_model
        )
    except Exception as e:
        logger.warning(f"Failed to fetch memory config from DB, using defaults: {e}")
        embedding_model = CONFIG.embedding_model
        extraction_model = CONFIG.extraction_model

    return {
        "embedding_model": embedding_model,
        "extraction_model": extraction_model,
    }


class Model(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    context_length: Optional[int] = None


class BaseProvider(ABC):
    def __init__(self, provider_id: str, config: Dict[str, Any]):
        self.provider_id = provider_id
        self.config = config

    @abstractmethod
    async def list_models(self) -> List[Model]:
        """Fetch or return list of available models."""
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Check if credentials are valid."""
        pass


class OpenAIProvider(BaseProvider):
    async def list_models(self) -> List[Model]:
        api_key = self.config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return []

        try:
            from litellm import get_valid_models

            with _temporary_env("OPENAI_API_KEY", api_key):
                loop = asyncio.get_running_loop()
                models_list = await loop.run_in_executor(
                    None,
                    lambda: get_valid_models(
                        check_provider_endpoint=True, custom_llm_provider="openai"
                    ),
                )

            return [Model(id=m, name=m) for m in models_list]

        except Exception as e:
            logger.error(
                f"Error fetching OpenAI models via litellm: {e}", exc_info=True
            )
            return []

    async def validate_credentials(self) -> bool:
        models = await self.list_models()
        return len(models) > 0


class OllamaProvider(BaseProvider):
    async def list_models(self) -> List[Model]:
        """Fetch models directly from Ollama's /api/tags endpoint."""
        base_url = (
            self.config.get("base_url")
            or os.environ.get("OLLAMA_BASE_URL")
            or "http://localhost:11434"
        )
        base_url = base_url.replace("/v1", "").rstrip("/")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{base_url}/api/tags") as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    models = []
                    for m in data.get("models", []):
                        name = f"ollama/{m['name']}"
                        models.append(Model(id=name, name=name))
                    return models
            except Exception as e:
                logger.error(f"Error fetching Ollama models: {e}")
                return []

    async def validate_credentials(self) -> bool:
        models = await self.list_models()
        return len(models) > 0


class LiteLLMProvider(BaseProvider):
    """Provider for LiteLLM Proxy -- queries the proxy's /v1/models endpoint."""

    async def list_models(self) -> List[Model]:
        base_url = (
            self.config.get("base_url")
            or self.config.get("LITELLM_BASE_URL")
            or os.environ.get("LITELLM_PROXY_API_BASE")
        )
        if not base_url:
            return []

        async with aiohttp.ClientSession() as session:
            try:
                target_url = base_url.rstrip("/")
                if not target_url.endswith("/v1"):
                    target_url += "/v1"

                api_key = (
                    self.config.get("api_key")
                    or self.config.get("LITELLM_MASTER_KEY")
                    or os.environ.get("LITELLM_PROXY_API_KEY")
                    or "sk-1234"
                )
                headers = {"Authorization": f"Bearer {api_key}"}

                async with session.get(f"{target_url}/models", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [
                            Model(id=m["id"], name=m["id"])
                            for m in data.get("data", [])
                        ]
            except Exception as e:
                logger.debug(f"LiteLLM auto-discovery failed: {e}")

        return []

    async def validate_credentials(self) -> bool:
        if self.config.get("base_url"):
            models = await self.list_models()
            return len(models) > 0
        return True


class GenericLiteLLMProvider(BaseProvider):
    """Provider that uses litellm's get_valid_models for Anthropic, Gemini, DeepSeek, etc."""

    _provider_env_keys = {
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }

    def _resolve_api_key(self) -> tuple[str, Optional[str]]:
        """
        Resolve the environment variable name and API key value for this provider.

        Returns:
            Tuple of (env_key, api_key_value). api_key_value may be None.
        """
        env_key = self._provider_env_keys.get(
            self.provider_id, f"{self.provider_id.upper()}_API_KEY"
        )

        # Check config first (direct key or field name)
        api_key_val = self.config.get("api_key") or self.config.get(env_key)

        # Fallback: scan config for anything that looks like a key/token
        if not api_key_val:
            for k, v in self.config.items():
                if isinstance(k, str) and ("KEY" in k or "TOKEN" in k) and v:
                    api_key_val = v
                    break

        # Final fallback: environment variable
        if not api_key_val:
            api_key_val = os.environ.get(env_key)

        return env_key, api_key_val

    async def list_models(self) -> List[Model]:
        from litellm import get_valid_models

        env_key, api_key_val = self._resolve_api_key()
        if not api_key_val:
            return []

        try:
            logger.info(
                f"Attempting discovery for {self.provider_id} with key length {len(api_key_val)}"
            )
            with _temporary_env(env_key, api_key_val):
                loop = asyncio.get_running_loop()
                models_list = await loop.run_in_executor(
                    None,
                    lambda: get_valid_models(
                        check_provider_endpoint=True,
                        custom_llm_provider=self.provider_id,
                    ),
                )
            logger.info(
                f"Discovery for {self.provider_id} returned {len(models_list)} models: {models_list[:3]}..."
            )
            return [Model(id=m, name=m) for m in models_list]
        except Exception as e:
            logger.error(
                f"Error discovering models for {self.provider_id}: {e}", exc_info=True
            )
            return []

    async def validate_credentials(self) -> bool:
        models = await self.list_models()
        return len(models) > 0


class ProviderFactory:
    _registry = {
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "litellm": LiteLLMProvider,
    }

    # Generic wrapper for others
    _generic_providers = ["anthropic", "gemini", "deepseek"]

    @classmethod
    def get_provider(cls, provider_id: str, config: Dict[str, Any]) -> BaseProvider:
        if provider_id in cls._registry:
            return cls._registry[provider_id](provider_id, config)

        if provider_id in cls._generic_providers:
            return GenericLiteLLMProvider(provider_id, config)

        raise ValueError(f"Unknown provider: {provider_id}")
