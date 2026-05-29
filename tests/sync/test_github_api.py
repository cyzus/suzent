import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from suzent.sync.github_api import (
    get_authenticated_user,
    github_token_expired_without_refresh,
    parse_owner_repo,
    public_clone_url,
    resolve_github_token,
)


class FakeKeyring:
    def __init__(self, value: str | None = None) -> None:
        self.value = value

    def get_password(self, service: str, username: str) -> str | None:
        return self.value

    def set_password(self, service: str, username: str, value: str) -> None:
        self.value = value


def test_parse_owner_repo():
    assert parse_owner_repo("alice/suzent-brain") == ("alice", "suzent-brain")
    assert parse_owner_repo("suzent-brain") == (None, "suzent-brain")


def test_public_clone_url():
    assert public_clone_url("alice", "brain") == "https://github.com/alice/brain.git"


def test_resolve_github_token_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    assert resolve_github_token() == "ghp_test"


def test_resolve_github_token_from_legacy_keyring(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    keyring = FakeKeyring("ghu_legacy")
    monkeypatch.setitem(sys.modules, "keyring", keyring)

    assert resolve_github_token() == "ghu_legacy"


def test_resolve_github_token_refreshes_expired_device_token(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("suzent.sync.github_api.time.time", lambda: 1_000.0)
    keyring = FakeKeyring(
        json.dumps(
            {
                "version": 1,
                "access_token": "ghu_old",
                "access_token_expires_at": 900.0,
                "refresh_token": "ghr_old",
                "refresh_token_expires_at": 10_000.0,
            }
        )
    )
    monkeypatch.setitem(sys.modules, "keyring", keyring)

    response = MagicMock()
    response.json.return_value = {
        "access_token": "ghu_new",
        "expires_in": 28_800,
        "refresh_token": "ghr_new",
        "refresh_token_expires_in": 15_768_000,
        "token_type": "bearer",
        "scope": "repo,read:user",
    }
    response.raise_for_status.return_value = None
    monkeypatch.setattr(
        "suzent.sync.github_api.httpx.post", lambda *args, **kwargs: response
    )

    assert resolve_github_token() == "ghu_new"
    stored = json.loads(keyring.value or "{}")
    assert stored["access_token"] == "ghu_new"
    assert stored["refresh_token"] == "ghr_new"
    assert stored["access_token_expires_at"] == 29_800.0


def test_expired_device_token_without_refresh_requires_reauth(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("suzent.sync.github_api.time.time", lambda: 1_000.0)
    keyring = FakeKeyring(
        json.dumps(
            {
                "version": 1,
                "access_token": "ghu_old",
                "access_token_expires_at": 900.0,
                "refresh_token": "ghr_old",
                "refresh_token_expires_at": 950.0,
            }
        )
    )
    monkeypatch.setitem(sys.modules, "keyring", keyring)

    assert resolve_github_token() is None
    assert github_token_expired_without_refresh() is True


def test_get_authenticated_user():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"login": "alice"}
    response.text = ""
    response.reason_phrase = "OK"

    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    client.request.return_value = response

    with patch("suzent.sync.github_api.httpx.Client", return_value=client):
        assert get_authenticated_user("ghp_test") == "alice"
