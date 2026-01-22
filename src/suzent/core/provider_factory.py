from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import os
import aiohttp
import asyncio
import logging
from suzent.config import CONFIG
import json


logger = logging.getLogger(__name__)

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
    """
    Helper to aggregate all enabled/available models from provider config.
    """
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

    all_models = []

    if not custom_config:
        # If user hasn't configured providers yet, check config.py defaults
        if CONFIG.model_options:
            return CONFIG.model_options

        # Fallback to internal defaults from PROVIDER_CONFIG
        defaults = []
        for p in PROVIDER_CONFIG:
            for m in p.get("default_models", []):
                defaults.append(m["id"])
        return sorted(list(set(defaults)))

    for p in PROVIDER_CONFIG:
        pid = p["id"]

        user_conf = custom_config.get(pid, {})
        enabled = set(user_conf.get("enabled_models", []))

        # Add enabled models
        for m in enabled:
            all_models.append(m)

    # Remove duplicates and sort
    return sorted(list(set(all_models)))


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
        # Use liteLLM's discovery which validates keys automatically
        api_key = self.config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return []

        try:
            # Temporarily inject key into env if provided in config but not env
            # litellm usually looks at env vars
            original_key = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = api_key

            from litellm import get_valid_models

            # Simple synchronous call
            # Using run_in_executor might be causing issues with context or pickling if not careful,
            # though usually it's fine. Let's try direct call in executor but handle potential errors better.

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
            # Fallback to manual check if litellm fails?
            return []
        finally:
            if "original_key" in locals():
                if original_key is None:
                    if "OPENAI_API_KEY" in os.environ:
                        del os.environ["OPENAI_API_KEY"]
                else:
                    os.environ["OPENAI_API_KEY"] = original_key

    async def validate_credentials(self) -> bool:
        # validate using list_models which does a check
        models = await self.list_models()
        return len(models) > 0


class OllamaProvider(BaseProvider):
    async def list_models(self) -> List[Model]:
        # Currently litellm's get_valid_models doesn't explicitly support Ollama local endpoint checks
        # in the same way as OpenAI (it usually checks keys).
        # However, we can try using it if we set the custom_llm_provider="ollama" and base_url.
        # But litellm documentation suggests it checks "endpoints" for specific providers.
        # Let's see if we can use it. If not, fallback to manual logic?
        # Actually, get_valid_models(check_provider_endpoint=True) for Ollama might need specific env vars.

        # For now, let's keep the reliable manual HTTP check for Ollama, as it doesn't require an API key
        # and litellm's focus is often on auth'd providers.
        # But we CAN update LiteLLMProvider to be generic.

        # Original simple logic for Ollama seems fine and robust for localhost.
        # Reverting to manual list for Ollama to ensure stability unless I verify litellm supports it fully.
        # But checking recent docs, litellm does support Ollama.

        return await self._manual_list_models()

    async def _manual_list_models(self) -> List[Model]:
        base_url = (
            self.config.get("base_url")
            or os.environ.get("OLLAMA_BASE_URL")
            or "http://localhost:11434"
        )
        base_url = base_url.replace("/v1", "")

        async with aiohttp.ClientSession() as session:
            try:
                base_url = base_url.rstrip("/")
                async with session.get(f"{base_url}/api/tags") as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    models = []
                    for m in data.get("models", []):
                        name = m["name"]
                        models.append(Model(id=name, name=name))
                    return models
            except Exception as e:
                logger.error(f"Error fetching Ollama models: {e}")
                return []

    async def validate_credentials(self) -> bool:
        # validate using list_models which does a check
        models = await self.list_models()
        return len(models) >= 0


class LiteLLMProvider(BaseProvider):
    async def list_models(self) -> List[Model]:
        # Generic LiteLLM provider can now use the powerful get_valid_models helper!
        # This will discover models for ANY provider if env vars are set properly?
        # Or if we have a Proxy Base URL.

        # If accessing a LiteLLM Proxy:
        base_url = (
            self.config.get("base_url")
            or self.config.get("LITELLM_BASE_URL")
            or os.environ.get("LITELLM_PROXY_API_BASE")
        )
        if base_url:
            # Proxy /v1/models check is standard
            async with aiohttp.ClientSession() as session:
                try:
                    target_url = base_url.rstrip("/")
                    if not target_url.endswith("/v1"):
                        target_url += "/v1"

                    # Dummy key if needed
                    api_key = (
                        self.config.get("api_key")
                        or self.config.get("LITELLM_MASTER_KEY")
                        or os.environ.get("LITELLM_PROXY_API_KEY")
                        or "sk-1234"
                    )
                    headers = {"Authorization": f"Bearer {api_key}"}

                    async with session.get(
                        f"{target_url}/models", headers=headers
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = []
                            for m in data.get("data", []):
                                mid = m["id"]
                                models.append(Model(id=mid, name=mid))
                            return models
                except Exception as e:
                    logger.debug(f"LiteLLM auto-discovery failed: {e}")

        # If authenticating directly via keys (no proxy url), try to discover
        # supported models for set keys?
        # That's harder because we need to know WHICH provider to check.
        # But we can try checking specific ones if keys are present.

        # For now, if no Proxy URL, return empty (custom models only)
        return []

    async def validate_credentials(self) -> bool:
        if self.config.get("base_url"):
            _ = await self.list_models()
            return True
        return True


class GenericLiteLLMProvider(BaseProvider):
    async def list_models(self) -> List[Model]:
        # import os # REMOVED: Global import
        from litellm import get_valid_models

        provider_env_keys = {
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }

        env_key = provider_env_keys.get(self.provider_id)
        if not env_key:
            env_key = f"{self.provider_id.upper()}_API_KEY"

        # Try to find api_key from config
        api_key_val = self.config.get("api_key") or self.config.get(env_key)

        # If not, try checking fields for anything that looks like a key
        if not api_key_val:
            for k, v in self.config.items():
                if isinstance(k, str) and ("KEY" in k or "TOKEN" in k) and v:
                    api_key_val = v
                    break

        # Finally check os.environ if not in config
        if not api_key_val:
            api_key_val = os.environ.get(env_key)

        if not api_key_val:
            return []

        # Temporarily inject key
        original_val = os.environ.get(env_key)
        os.environ[env_key] = api_key_val

        try:
            logger.info(
                f"Attempting discovery for {self.provider_id} with key length {len(api_key_val)}"
            )
            loop = asyncio.get_running_loop()
            models_list = await loop.run_in_executor(
                None,
                lambda: get_valid_models(
                    check_provider_endpoint=True, custom_llm_provider=self.provider_id
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
        finally:
            if original_val is None:
                if env_key in os.environ:
                    del os.environ[env_key]
            else:
                os.environ[env_key] = original_val

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
