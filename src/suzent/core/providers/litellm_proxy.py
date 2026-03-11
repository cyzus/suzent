from __future__ import annotations

import os
from typing import List

import aiohttp

from suzent.core.providers.base import BaseProvider, Model, prefixed
from suzent.logger import get_logger

logger = get_logger(__name__)


class LiteLLMProxyProvider(BaseProvider):
    """Provider for a self-hosted LiteLLM Proxy — queries /v1/models."""

    async def list_models(self) -> List[Model]:
        base_url = (
            self.config.get("base_url")
            or self.config.get("LITELLM_BASE_URL")
            or os.environ.get("LITELLM_PROXY_API_BASE")
        )
        if not base_url:
            return []

        target_url = base_url.rstrip("/")
        if not target_url.endswith("/v1"):
            target_url += "/v1"

        api_key = (
            self.config.get("api_key")
            or self.config.get("LITELLM_MASTER_KEY")
            or os.environ.get("LITELLM_PROXY_API_KEY")
            or "sk-1234"
        )

        async with aiohttp.ClientSession() as session:
            try:
                headers = {"Authorization": f"Bearer {api_key}"}
                async with session.get(f"{target_url}/models", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [
                            Model(id=prefixed(self.provider_id, m["id"]), name=m["id"])
                            for m in data.get("data", [])
                        ]
            except Exception as e:
                logger.debug(f"LiteLLM proxy discovery failed: {e}")

        return []

    async def validate_credentials(self) -> bool:
        has_url = (
            self.config.get("base_url")
            or self.config.get("LITELLM_BASE_URL")
            or os.environ.get("LITELLM_PROXY_API_BASE")
        )
        if has_url:
            return len(await self.list_models()) > 0
        return True
