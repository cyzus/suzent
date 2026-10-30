"""The one place sync code runs git.

GitHub credentials are passed to git through ``GIT_CONFIG_*`` environment
variables as an ``http.extraHeader`` scoped to github.com, the same way
``actions/checkout`` does it. The token never appears in a command line, a
remote URL, or ``.git/config``, so it cannot leak through the process list or
a git error message.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path

GITHUB_HTTPS_PREFIX = "https://github.com/"

_URL_CREDENTIAL_RE = re.compile(r"(https://)([^/@\s]+)@")
_ACCESS_TOKEN_RE = re.compile(r"(x-access-token:)[^/@\s]+")
_AUTH_HEADER_RE = re.compile(r"(AUTHORIZATION: basic )\S+", re.IGNORECASE)


def run_git(cwd: Path | None, *args: str, token: str | None = None) -> str:
    """Run ``git <args>`` in ``cwd`` and return stdout, raising RuntimeError on failure.

    With ``token``, requests to github.com over HTTPS are authenticated and
    interactive credential prompts are disabled.
    """
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=github_auth_env(token) if token else None,
    )
    if completed.returncode != 0:
        detail = redact_git_credentials(
            completed.stderr.strip() or completed.stdout.strip()
        )
        command = " ".join(redact_git_credentials(arg) for arg in args)
        raise RuntimeError(f"git {command} failed: {detail}")
    return completed.stdout


def git_config_value(cwd: Path, key: str) -> str:
    """Return ``git config <key>`` in ``cwd``, or an empty string if unset."""
    try:
        return run_git(cwd, "config", key).strip()
    except RuntimeError:
        return ""


def git_remote_names(repo_path: Path) -> list[str]:
    """List the remotes configured in ``repo_path``; empty list if git fails."""
    try:
        output = run_git(repo_path, "remote")
    except RuntimeError:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def is_github_https_url(url: str) -> bool:
    return url.lower().startswith(GITHUB_HTTPS_PREFIX)


def github_auth_env(token: str) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["SSH_ASKPASS"] = ""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    index = int(env.get("GIT_CONFIG_COUNT", "0") or 0)
    env["GIT_CONFIG_COUNT"] = str(index + 1)
    env[f"GIT_CONFIG_KEY_{index}"] = f"http.{GITHUB_HTTPS_PREFIX}.extraheader"
    env[f"GIT_CONFIG_VALUE_{index}"] = f"AUTHORIZATION: basic {basic}"
    return env


def redact_git_credentials(value: str) -> str:
    redacted = _ACCESS_TOKEN_RE.sub(r"\1<redacted>", value)
    redacted = _AUTH_HEADER_RE.sub(r"\1<redacted>", redacted)
    return _URL_CREDENTIAL_RE.sub(r"\1<redacted>@", redacted)
