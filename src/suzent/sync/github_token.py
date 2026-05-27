from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from suzent.sync.github_api import authed_clone_url, resolve_github_token


def github_token_configured() -> bool:
    return resolve_github_token() is not None


def git_push_with_token(cwd: Path, token: str, remote_url: str, branch: str) -> str:
    return _run_git(cwd, "push", remote_url, branch, extra_env=_git_auth_env())


def git_fetch_with_token(cwd: Path, token: str, remote_url: str, branch: str) -> str:
    return _run_git(cwd, "fetch", remote_url, branch, extra_env=_git_auth_env())


def git_pull_with_token(cwd: Path, token: str, remote_url: str, branch: str) -> str:
    return _run_git(
        cwd,
        "pull",
        "--ff-only",
        remote_url,
        branch,
        extra_env=_git_auth_env(),
    )


def authed_remote_for_push(public_remote_url: str, token: str | None) -> str:
    if not token:
        return public_remote_url
    prefix = "https://github.com/"
    if not public_remote_url.startswith(prefix):
        return public_remote_url
    rest = public_remote_url.removeprefix(prefix).removesuffix(".git")
    if "/" not in rest:
        return public_remote_url
    owner, repo = rest.split("/", 1)
    return authed_clone_url(owner, repo, token)


def _git_auth_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["SSH_ASKPASS"] = ""
    return env


def _run_git(cwd: Path, *args: str, extra_env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=extra_env,
    )
    if completed.returncode != 0:
        detail = _redact_git_credentials(
            completed.stderr.strip() or completed.stdout.strip()
        )
        command = " ".join(_redact_git_credentials(arg) for arg in args)
        raise RuntimeError(f"git {command} failed: {detail}")
    return completed.stdout


_URL_CREDENTIAL_RE = re.compile(r"(https://)([^/@\s]+)@")
_ACCESS_TOKEN_RE = re.compile(r"(x-access-token:)[^/@\s]+")


def _redact_git_credentials(value: str) -> str:
    redacted = _ACCESS_TOKEN_RE.sub(r"\1<redacted>", value)
    return _URL_CREDENTIAL_RE.sub(r"\1<redacted>@", redacted)
