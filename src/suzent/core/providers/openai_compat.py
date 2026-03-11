from __future__ import annotations

from typing import List

import aiohttp

from suzent.core.providers.base import BaseProvider, Model
from suzent.core.providers.helpers import resolve_api_key
from suzent.logger import get_logger

logger = get_logger(__name__)


class OpenAICompatProvider(BaseProvider):
    """Provider for any OpenAI-compatible API (MiniMax, Moonshot/Kimi, Zhipu/GLM, etc.).

    Attempts to discover models via GET /models. If the provider doesn't support
    that endpoint (404 or error), falls back to the catalog's default_models.
    """

    def __init__(self, provider_id: str, config: dict, base_url: str):
        super().__init__(provider_id, config)
        self.base_url = base_url.rstrip("/")

    def _catalog_defaults(self) -> List[Model]:
        """Return default models from the catalog for this provider."""
        from suzent.core.providers.catalog import PROVIDER_CONFIG_BY_ID

        entry = PROVIDER_CONFIG_BY_ID.get(self.provider_id)
        if entry:
            return [
                Model(id=m["id"], name=m["name"])
                for m in entry.get("default_models", [])
            ]
        return []

    async def list_models(self) -> List[Model]:
        api_key = resolve_api_key(self.provider_id, self.config)
        if not api_key:
            return []

        headers = {"Authorization": f"Bearer {api_key}"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.base_url}/models",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("data", data.get("models", []))
                        result = []
                        for m in items:
                            raw_id = m.get("id") or m.get("model") or str(m)
                            prefixed = (
                                raw_id
                                if raw_id.startswith(f"{self.provider_id}/")
                                else f"{self.provider_id}/{raw_id}"
                            )
                            result.append(Model(id=prefixed, name=raw_id))
                        if result:
                            return result

                    logger.debug(
                        f"{self.provider_id} /models returned {resp.status}, "
                        f"falling back to catalog defaults"
                    )
            except Exception as e:
                logger.debug(
                    f"{self.provider_id} model discovery failed ({e}), using catalog defaults"
                )

        return self._catalog_defaults()

    async def validate_credentials(self) -> bool:
        # Key must exist; model list (live or catalog) confirms the provider is reachable.
        if not resolve_api_key(self.provider_id, self.config):
            return False
        return await super().validate_credentials()
