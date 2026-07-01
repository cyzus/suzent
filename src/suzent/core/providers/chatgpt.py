from __future__ import annotations

from typing import List

from suzent.core.providers.base import BaseProvider, Model, prefixed
from suzent.core.providers.chatgpt_auth import (
    ChatGPTAuthUnavailable,
    chatgpt_api_base,
    chatgpt_default_headers,
    create_authenticator,
    get_account_id,
    get_litellm_httpx_client,
    get_valid_access_token,
)
from suzent.logger import get_logger

logger = get_logger(__name__)


class ChatGPTProvider(BaseProvider):
    """ChatGPT subscription provider — auth via LiteLLM device-code OAuth."""

    def _authenticator(self):
        return create_authenticator()

    def is_authenticated(self) -> bool:
        auth = self._authenticator()
        return bool(get_valid_access_token(auth))

    def fetch_models(self) -> List[Model]:
        auth = self._authenticator()
        token = get_valid_access_token(auth)
        if not token:
            return []

        try:
            headers = chatgpt_default_headers(token, get_account_id(auth))
            client = get_litellm_httpx_client()
            resp = client.get(
                f"{chatgpt_api_base()}/models",
                headers=headers,
                params={"client_version": "0.0.0"},
            )
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return [
                Model(id=prefixed("chatgpt", m["slug"]), name=m["display_name"])
                for m in models
                if m.get("slug") and m.get("supported_in_api", True)
            ]
        except Exception as exc:
            logger.warning("Failed to fetch ChatGPT models: {}", exc)
            return []

    async def list_models(self) -> List[Model]:
        import asyncio

        try:
            if not self.is_authenticated():
                return []
            return await asyncio.to_thread(self.fetch_models)
        except ChatGPTAuthUnavailable as exc:
            logger.warning("ChatGPT auth unavailable: {}", exc)
            return []
