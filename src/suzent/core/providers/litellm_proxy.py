from __future__ import annotations

import os
from typing import List, Optional

import aiohttp

from suzent.core.providers.base import BaseProvider, Model, prefixed
from suzent.logger import get_logger

logger = get_logger(__name__)


def _saved_value(*keys: str) -> Optional[str]:
    """First non-empty value among ``keys`` from the secret store or environment.

    Settings saves the proxy fields under ``LITELLM_BASE_URL`` and
    ``LITELLM_MASTER_KEY``, and once saved the UI sends an empty config on
    verify, so discovery has to read them back from here.
    """
    try:
        from suzent.core.secrets import get_secret_manager

        sm = get_secret_manager()
    except Exception:
        sm = None
    for key in keys:
        value = (sm.get(key) if sm else None) or os.environ.get(key)
        if value:
            return value
    return None


class LiteLLMProxyProvider(BaseProvider):
    """Provider for a self-hosted LiteLLM Proxy — queries /v1/models."""

    def _base_url(self) -> Optional[str]:
        return (
            self.config.get("base_url")
            or self.config.get("LITELLM_BASE_URL")
            or _saved_value("LITELLM_BASE_URL", "LITELLM_PROXY_API_BASE")
        )

    def _api_key(self) -> str:
        return (
            self.config.get("api_key")
            or self.config.get("LITELLM_MASTER_KEY")
            or _saved_value("LITELLM_MASTER_KEY", "LITELLM_PROXY_API_KEY")
            or "sk-1234"
        )

    async def list_models(self) -> List[Model]:
        base_url = self._base_url()
        if not base_url:
            logger.debug("LiteLLM proxy discovery skipped: no base URL configured")
            return []

        target_url = base_url.rstrip("/")
        if not target_url.endswith("/v1"):
            target_url += "/v1"

        async with aiohttp.ClientSession() as session:
            try:
                headers = {"Authorization": f"Bearer {self._api_key()}"}
                async with session.get(
                    f"{target_url}/models",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [
                            Model(id=prefixed(self.provider_id, m["id"]), name=m["id"])
                            for m in data.get("data", [])
                        ]
                    logger.warning(
                        "LiteLLM proxy discovery at {}/models returned HTTP {}",
                        target_url,
                        resp.status,
                    )
            except Exception as e:
                logger.warning(f"LiteLLM proxy discovery failed: {e}")

        return []

    async def validate_credentials(self) -> bool:
        if self._base_url():
            return len(await self.list_models()) > 0
        return True
