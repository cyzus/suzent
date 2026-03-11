from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

from suzent.core.providers.base import BaseProvider, Model, _temporary_env, prefixed
from suzent.core.providers.catalog import PROVIDER_ENV_KEYS
from suzent.core.providers.helpers import resolve_api_key
from suzent.logger import get_logger

logger = get_logger(__name__)


class GenericLiteLLMProvider(BaseProvider):
    """Catch-all provider that uses litellm's get_valid_models for discovery.

    Works for any provider supported by LiteLLM — Anthropic, Gemini, Mistral,
    DeepSeek, MiniMax, Moonshot, Zhipu AI, and others.
    """

    def _resolve_api_key(self) -> Tuple[str, Optional[str]]:
        env_keys = PROVIDER_ENV_KEYS.get(
            self.provider_id, [f"{self.provider_id.upper()}_API_KEY"]
        )
        env_key = env_keys[0] if env_keys else f"{self.provider_id.upper()}_API_KEY"
        api_key_val = resolve_api_key(self.provider_id, self.config)
        return env_key, api_key_val

    async def list_models(self) -> List[Model]:
        from litellm import get_valid_models

        env_key, api_key_val = self._resolve_api_key()
        if not api_key_val:
            return []

        try:
            logger.info(f"Discovering models for {self.provider_id}")
            with _temporary_env(env_key, api_key_val):
                loop = asyncio.get_running_loop()
                models_list = await loop.run_in_executor(
                    None,
                    lambda: get_valid_models(
                        check_provider_endpoint=True,
                        custom_llm_provider=self.provider_id,
                    ),
                )
            logger.info(f"Found {len(models_list)} models for {self.provider_id}")
            # LiteLLM returns bare names like "deepseek-chat"; prefix so model_factory can route.
            return [
                Model(id=prefixed(self.provider_id, m), name=m) for m in models_list
            ]
        except Exception as e:
            logger.error(
                f"Error discovering models for {self.provider_id}: {e}", exc_info=True
            )
            return []
