from unittest.mock import MagicMock, patch

import pytest

from suzent.sync.github_api import (
    get_authenticated_user,
    parse_owner_repo,
    public_clone_url,
    resolve_github_token,
)


def test_parse_owner_repo():
    assert parse_owner_repo("alice/suzent-brain") == ("alice", "suzent-brain")
    assert parse_owner_repo("suzent-brain") == (None, "suzent-brain")


def test_public_clone_url():
    assert public_clone_url("alice", "brain") == "https://github.com/alice/brain.git"


def test_resolve_github_token_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    assert resolve_github_token() == "ghp_test"


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
