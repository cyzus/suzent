from __future__ import annotations

import os
import subprocess
from pathlib import Path

from suzent.sync.github_api import authed_clone_url, resolve_github_token


def github_token_configured() -> bool:
    return resolve_github_token() is not None


def git_push_with_token(cwd: Path, token: str, remote_url: str, branch: str) -> str:
    return _run_git(cwd, "push", remote_url, branch, extra_env=_git_auth_env(token))


def git_fetch_with_token(
    cwd: Path, token: str, remote_url: str, branch: str
) -> str:
    return _run_git(cwd, "fetch", remote_url, branch, extra_env=_git_auth_env(token))


def git_pull_with_token(
    cwd: Path, token: str, remote_url: str, branch: str
) -> str:
    return _run_git(
        cwd,
        "pull",
        "--ff-only",
        remote_url,
        branch,
        extra_env=_git_auth_env(token),
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


def _git_auth_env(token: str) -> dict[str, str]:
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
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout
