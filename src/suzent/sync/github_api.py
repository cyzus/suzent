from __future__ import annotations

import os
import re
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"
KEYRING_SERVICE = "suzent"
KEYRING_USERNAME = "github-sync-token"
OWNER_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class GitHubApiError(RuntimeError):
    pass


def resolve_github_token(explicit: str | None = None) -> str | None:
    token = (explicit or "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:
        import keyring

        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None
    return stored.strip() if stored else None


def store_github_token(token: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token.strip())


def clear_github_token() -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass


def parse_owner_repo(value: str) -> tuple[str | None, str]:
    raw = value.strip()
    if OWNER_REPO_RE.fullmatch(raw):
        owner, name = raw.split("/", 1)
        return owner, name
    return None, raw


def authed_clone_url(owner: str, repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"


def public_clone_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}.git"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(token: str, method: str, path: str, **kwargs: Any) -> httpx.Response:
    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            method,
            f"{GITHUB_API}{path}",
            headers=_headers(token),
            **kwargs,
        )
    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise GitHubApiError(f"GitHub API {path} failed ({response.status_code}): {detail}")
    return response


def get_authenticated_user(token: str) -> str:
    response = _request(token, "GET", "/user")
    data = response.json()
    login = str(data.get("login", "")).strip()
    if not login:
        raise GitHubApiError("GitHub user login is empty")
    return login


def repo_exists(token: str, owner: str, repo: str) -> bool:
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers=_headers(token),
        timeout=30.0,
    )
    if response.status_code == 404:
        return False
    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise GitHubApiError(
            f"GitHub API /repos/{owner}/{repo} failed ({response.status_code}): {detail}"
        )
    return True


def create_private_repo(token: str, name: str, *, description: str) -> str:
    _request(
        token,
        "POST",
        "/user/repos",
        json={
            "name": name,
            "private": True,
            "description": description,
            "auto_init": False,
        },
    )
    return name
