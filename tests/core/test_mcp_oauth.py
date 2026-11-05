"""OAuth tokens for hosted MCP servers: persisted in secrets, sign-in only from Settings."""

import pytest
from mcp.shared.auth import OAuthToken

from suzent.core import mcp_oauth
from suzent.core import secrets as secrets_module
from suzent.core.secrets import SecretManager


class _DictBackend:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)

    def list_keys(self):
        return list(self.values)


@pytest.fixture
def secrets(monkeypatch):
    backend = _DictBackend()
    monkeypatch.setattr(secrets_module, "_instance", SecretManager(backend))
    return backend


URL = "https://mcp.example.com/mcp"


async def test_tokens_survive_a_new_provider(secrets):
    """A restart builds a new provider; it must find the stored tokens."""
    first = mcp_oauth.build_oauth("notion.notion", URL)
    await first.token_storage_adapter.set_tokens(
        OAuthToken(access_token="a1", refresh_token="r1", expires_in=3600)
    )
    assert mcp_oauth.has_stored_tokens("notion.notion")

    second = mcp_oauth.build_oauth("notion.notion", URL)
    tokens = await second.token_storage_adapter.get_tokens()
    assert tokens is not None and tokens.refresh_token == "r1"
    # Every record lives under the private prefix, never exported to env.
    assert all(secrets_module.is_private_key(k) for k in secrets.values)


async def test_sign_out_forgets_only_that_server(secrets):
    for namespace in ("notion.notion", "linear.linear"):
        provider = mcp_oauth.build_oauth(namespace, URL)
        await provider.token_storage_adapter.set_tokens(
            OAuthToken(access_token="a", refresh_token="r")
        )

    mcp_oauth.sign_out("notion.notion")

    assert not mcp_oauth.has_stored_tokens("notion.notion")
    assert mcp_oauth.has_stored_tokens("linear.linear")


async def test_a_run_never_opens_the_browser(secrets):
    provider = mcp_oauth.build_oauth("notion.notion", URL)
    with pytest.raises(mcp_oauth.SignInRequired):
        await provider.redirect_handler("https://auth.example.com/authorize")


async def test_a_sign_in_hands_the_url_to_the_caller(secrets):
    seen = []
    provider = mcp_oauth.build_oauth("notion.notion", URL, on_authorize=seen.append)
    await provider.redirect_handler("https://auth.example.com/authorize?x=1")
    assert seen == ["https://auth.example.com/authorize?x=1"]
