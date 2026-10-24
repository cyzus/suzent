from __future__ import annotations

import os
from typing import Any

import aiohttp

from suzent.core.providers.base import BaseProvider, Model, prefixed
from suzent.core.providers.helpers import resolve_api_key
from suzent.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(BaseProvider):
    async def list_models(self) -> list[Model]:
        api_key = resolve_api_key("openai", self.config)
        if not api_key:
            return []

        base_url = self.config.get("OPENAI_BASE_URL") or os.environ.get(
            "OPENAI_BASE_URL"
        )
        if not base_url:
            try:
                from suzent.core.secrets import get_secret_manager

                base_url = get_secret_manager().get("OPENAI_BASE_URL")
            except Exception:
                logger.debug(
                    "OpenAI base URL could not be read; using the default endpoint"
                )
        base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    response.raise_for_status()
                    data: dict[str, Any] = await response.json()
            return [
                Model(id=prefixed("openai", item["id"]), name=item["id"])
                for item in data.get("data", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            logger.warning("OpenAI model discovery failed: {}", type(exc).__name__)
            return []
