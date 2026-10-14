from __future__ import annotations

from typing import Any

import pytest

from suzent.core.providers import litellm_proxy
from suzent.core.providers.litellm_proxy import LiteLLMProxyProvider


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return {"data": [{"id": "gpt-4o"}, {"id": "claude-sonnet"}]}


class _FakeSession:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.last_url: str | None = None
        self.last_headers: dict[str, str] | None = None

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def get(self, url: str, *, headers: dict[str, str], timeout: Any) -> _FakeResponse:
        self.last_url = url
        self.last_headers = headers
        return _FakeResponse(self.status)


class _FakeSecrets:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, key: str) -> str | None:
        return self.values.get(key)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch) -> None:
    for key in (
        "LITELLM_BASE_URL",
        "LITELLM_MASTER_KEY",
        "LITELLM_PROXY_API_BASE",
        "LITELLM_PROXY_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.asyncio
async def test_discovery_reads_saved_settings_when_config_is_empty(
    monkeypatch,
) -> None:
    session = _FakeSession()
    monkeypatch.setattr(litellm_proxy.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(
        "suzent.core.secrets.get_secret_manager",
        lambda: _FakeSecrets(
            {
                "LITELLM_BASE_URL": "https://proxy.example.com/",
                "LITELLM_MASTER_KEY": "sk-saved",
            }
        ),
    )

    models = await LiteLLMProxyProvider("litellm_proxy", {}).list_models()

    assert [m.id for m in models] == [
        "litellm_proxy/gpt-4o",
        "litellm_proxy/claude-sonnet",
    ]
    assert session.last_url == "https://proxy.example.com/v1/models"
    assert session.last_headers == {"Authorization": "Bearer sk-saved"}


@pytest.mark.asyncio
async def test_config_overrides_saved_settings(monkeypatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr(litellm_proxy.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(
        "suzent.core.secrets.get_secret_manager",
        lambda: _FakeSecrets({"LITELLM_BASE_URL": "https://old.example.com"}),
    )

    await LiteLLMProxyProvider(
        "litellm_proxy",
        {
            "LITELLM_BASE_URL": "http://localhost:4000/v1",
            "LITELLM_MASTER_KEY": "sk-new",
        },
    ).list_models()

    assert session.last_url == "http://localhost:4000/v1/models"
    assert session.last_headers == {"Authorization": "Bearer sk-new"}


@pytest.mark.asyncio
async def test_unauthorized_proxy_returns_no_models(monkeypatch) -> None:
    session = _FakeSession(status=401)
    monkeypatch.setattr(litellm_proxy.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(
        "suzent.core.secrets.get_secret_manager",
        lambda: _FakeSecrets({"LITELLM_BASE_URL": "https://proxy.example.com"}),
    )

    assert await LiteLLMProxyProvider("litellm_proxy", {}).list_models() == []


@pytest.mark.asyncio
async def test_secret_store_failure_falls_back_to_environment(monkeypatch) -> None:
    class _BrokenSecrets:
        def get(self, _key: str) -> str | None:
            raise RuntimeError("keyring unavailable")

    session = _FakeSession()
    monkeypatch.setattr(litellm_proxy.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr("suzent.core.secrets.get_secret_manager", _BrokenSecrets)
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", "http://localhost:4000")

    await LiteLLMProxyProvider("litellm_proxy", {}).list_models()

    assert session.last_url == "http://localhost:4000/v1/models"
