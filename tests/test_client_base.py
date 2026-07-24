from unittest.mock import patch

import pytest

from suzent.client.base import AsyncBaseClient, _is_loopback_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:25314",
        "http://LOCALHOST.:25314",
        "http://agent.localhost:25314",
        "http://127.0.0.1:25314",
        "http://127.42.0.9:25314",
        "http://[::1]:25314",
        "http://[::ffff:127.0.0.1]:25314",
    ],
)
def test_is_loopback_url(url: str) -> None:
    assert _is_loopback_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://192.168.1.20:25314",
        "http://localhost.example.com:25314",
    ],
)
def test_is_loopback_url_rejects_remote_hosts(url: str) -> None:
    assert not _is_loopback_url(url)


def test_client_ignores_environment_proxy_for_loopback_url() -> None:
    with patch("suzent.client.base.httpx.AsyncClient") as async_client:
        AsyncBaseClient("http://localhost:25314")

    async_client.assert_called_once_with(
        base_url="http://localhost:25314",
        timeout=30.0,
        trust_env=False,
    )


def test_client_keeps_environment_proxy_for_remote_url() -> None:
    with patch("suzent.client.base.httpx.AsyncClient") as async_client:
        AsyncBaseClient("https://suzent.example.com")

    async_client.assert_called_once_with(
        base_url="https://suzent.example.com",
        timeout=30.0,
        trust_env=True,
    )
