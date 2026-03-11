from __future__ import annotations

import os
from typing import List

import aiohttp

from suzent.core.providers.base import BaseProvider, Model
from suzent.logger import get_logger

logger = get_logger(__name__)


class OllamaProvider(BaseProvider):
    async def list_models(self) -> List[Model]:
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
                    return [
                        Model(id=f"ollama/{m['name']}", name=f"ollama/{m['name']}")
                        for m in data.get("models", [])
                    ]
            except Exception as e:
                logger.error(f"Error fetching Ollama models: {e}")
                return []

    async def validate_credentials(self) -> bool:
        return len(await self.list_models()) > 0
