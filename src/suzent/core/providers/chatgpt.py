from __future__ import annotations

from typing import List

from suzent.core.providers.base import BaseProvider, Model, prefixed
from suzent.logger import get_logger

logger = get_logger(__name__)


class ChatGPTProvider(BaseProvider):
    """ChatGPT subscription provider — auth via LiteLLM device-code OAuth."""

    def _authenticator(self):
        from litellm.llms.chatgpt.authenticator import Authenticator

        return Authenticator()

    def is_authenticated(self) -> bool:
        auth = self._authenticator()
        data = auth._read_auth_file()
        if not data:
            return False
        token = data.get("access_token")
        return bool(token and not auth._is_token_expired(data, token))

    def fetch_models(self) -> List[Model]:
        from litellm.llms.chatgpt.common_utils import (
            CHATGPT_API_BASE,
            get_chatgpt_default_headers,
        )
        from litellm.llms.custom_httpx.http_handler import _get_httpx_client

        auth = self._authenticator()
        data = auth._read_auth_file() or {}
        token = data.get("access_token")
        if not token:
            return []

        try:
            headers = get_chatgpt_default_headers(token, auth.get_account_id())
            client = _get_httpx_client()
            resp = client.get(
                f"{CHATGPT_API_BASE}/models",
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

        if not self.is_authenticated():
            return []
        return await asyncio.to_thread(self.fetch_models)
