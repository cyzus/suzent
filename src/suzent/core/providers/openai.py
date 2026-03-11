from __future__ import annotations

import asyncio
from typing import List

from suzent.core.providers.base import BaseProvider, Model, _temporary_env, prefixed
from suzent.core.providers.helpers import resolve_api_key
from suzent.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(BaseProvider):
    async def list_models(self) -> List[Model]:
        api_key = resolve_api_key("openai", self.config)
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

            return [Model(id=prefixed("openai", m), name=m) for m in models_list]

        except Exception as e:
            logger.error(f"Error fetching OpenAI models: {e}", exc_info=True)
            return []
