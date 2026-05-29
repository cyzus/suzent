from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from suzent.sync.github_device_flow import GITHUB_APP_CLIENT_ID

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
KEYRING_SERVICE = "suzent"
KEYRING_USERNAME = "github-sync-token"
OWNER_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_TOKEN_REFRESH_SKEW_SECONDS = 5 * 60


class GitHubApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredGitHubToken:
    access_token: str
    access_token_expires_at: float | None = None
    refresh_token: str | None = None
    refresh_token_expires_at: float | None = None
    token_type: str | None = None
    scope: str | None = None

    def is_access_token_fresh(self, now: float | None = None) -> bool:
        if not self.access_token:
            return False
        if self.access_token_expires_at is None:
            return True
        now = time.time() if now is None else now
        return self.access_token_expires_at - _TOKEN_REFRESH_SKEW_SECONDS > now

    def can_refresh(self, now: float | None = None) -> bool:
        if not self.refresh_token:
            return False
        if self.refresh_token_expires_at is None:
            return True
        now = time.time() if now is None else now
        return self.refresh_token_expires_at - _TOKEN_REFRESH_SKEW_SECONDS > now

    def expired_without_refresh(self, now: float | None = None) -> bool:
        return not self.is_access_token_fresh(now) and not self.can_refresh(now)


def resolve_github_token(explicit: str | None = None) -> str | None:
    token = (explicit or "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    stored = _load_stored_github_token()
    if stored is None:
        return None
    if stored.is_access_token_fresh():
        return stored.access_token
    if not stored.can_refresh():
        return None
    try:
        refreshed = refresh_github_token(stored.refresh_token)
    except GitHubApiError:
        return None
    store_github_token(
        refreshed.access_token,
        expires_in=_seconds_until(refreshed.access_token_expires_at),
        refresh_token=refreshed.refresh_token,
        refresh_token_expires_in=_seconds_until(refreshed.refresh_token_expires_at),
        token_type=refreshed.token_type,
        scope=refreshed.scope,
    )
    return refreshed.access_token


def github_token_expired_without_refresh() -> bool:
    stored = _load_stored_github_token()
    return bool(stored and stored.expired_without_refresh())


def _load_stored_github_token() -> StoredGitHubToken | None:
    try:
        import keyring

        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None
    return _parse_stored_github_token(stored)


def store_github_token(
    token: str,
    *,
    expires_in: int | None = None,
    refresh_token: str | None = None,
    refresh_token_expires_in: int | None = None,
    token_type: str | None = None,
    scope: str | None = None,
) -> None:
    import keyring

    token = token.strip()
    if (
        expires_in is None
        and refresh_token is None
        and refresh_token_expires_in is None
    ):
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
        return

    now = time.time()
    payload = {
        "version": 1,
        "access_token": token,
        "access_token_expires_at": _expires_at(now, expires_in),
        "refresh_token": refresh_token.strip() if refresh_token else None,
        "refresh_token_expires_at": _expires_at(now, refresh_token_expires_in),
        "token_type": token_type,
        "scope": scope,
    }
    keyring.set_password(
        KEYRING_SERVICE,
        KEYRING_USERNAME,
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
    )


def clear_github_token() -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass


def refresh_github_token(refresh_token: str | None) -> StoredGitHubToken:
    if not refresh_token:
        raise GitHubApiError("GitHub refresh token is missing")
    try:
        response = httpx.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": GITHUB_APP_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GitHubApiError(f"GitHub token refresh failed: {exc}") from exc
    data = response.json()
    if "error" in data:
        detail = data.get("error_description", data["error"])
        raise GitHubApiError(f"GitHub token refresh failed: {detail}")
    stored = _stored_token_from_response(data)
    if stored is None:
        raise GitHubApiError("GitHub token refresh response did not include a token")
    return stored


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


def _parse_stored_github_token(value: str | None) -> StoredGitHubToken | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if not raw.startswith("{"):
        return StoredGitHubToken(access_token=raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return StoredGitHubToken(access_token=raw)
    if not isinstance(data, dict):
        return None
    access_token = str(data.get("access_token", "")).strip()
    if not access_token:
        return None
    return StoredGitHubToken(
        access_token=access_token,
        access_token_expires_at=_optional_float(data.get("access_token_expires_at")),
        refresh_token=_optional_str(data.get("refresh_token")),
        refresh_token_expires_at=_optional_float(data.get("refresh_token_expires_at")),
        token_type=_optional_str(data.get("token_type")),
        scope=_optional_str(data.get("scope")),
    )


def _stored_token_from_response(data: dict[str, Any]) -> StoredGitHubToken | None:
    access_token = str(data.get("access_token", "")).strip()
    if not access_token:
        return None
    now = time.time()
    return StoredGitHubToken(
        access_token=access_token,
        access_token_expires_at=_expires_at(now, _optional_int(data.get("expires_in"))),
        refresh_token=_optional_str(data.get("refresh_token")),
        refresh_token_expires_at=_expires_at(
            now, _optional_int(data.get("refresh_token_expires_in"))
        ),
        token_type=_optional_str(data.get("token_type")),
        scope=_optional_str(data.get("scope")),
    )


def _expires_at(now: float, seconds: int | None) -> float | None:
    return now + seconds if seconds is not None else None


def _seconds_until(expires_at: float | None) -> int | None:
    if expires_at is None:
        return None
    return max(0, int(expires_at - time.time()))


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


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
        raise GitHubApiError(
            f"GitHub API {path} failed ({response.status_code}): {detail}"
        )
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
        message = f"GitHub API /repos/{owner}/{repo} failed"
        raise GitHubApiError(f"{message} ({response.status_code}): {detail}")
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
