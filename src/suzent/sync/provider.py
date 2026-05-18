from __future__ import annotations

import subprocess
from pathlib import Path

from suzent.logger import get_logger
from suzent.sync.github_api import resolve_github_token
from suzent.sync.github_token import (
    authed_remote_for_push,
    git_fetch_with_token,
    git_pull_with_token,
    git_push_with_token,
)
from suzent.sync.payload import PAYLOAD_DIR_NAME

logger = get_logger(__name__)


class GitHubSyncProvider:
    def __init__(self, repo_path: Path, *, remote: str = "origin", branch: str = "main"):
        self.repo_path = repo_path.expanduser().resolve()
        self.remote = remote
        self.branch = branch

    def validate(self, *, require_clean: bool = True) -> dict[str, str | bool]:
        if not self.repo_path.exists():
            raise FileNotFoundError(str(self.repo_path))
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"{self.repo_path} is not a Git repository")

        remote_url = self._git("remote", "get-url", self.remote).strip()
        if "github.com" not in remote_url.lower() and not Path(remote_url).exists():
            raise ValueError(f"Remote '{self.remote}' is not a GitHub remote")

        current_branch = self._git("branch", "--show-current").strip()
        if current_branch != self.branch:
            raise ValueError(
                f"Expected branch '{self.branch}', currently on '{current_branch}'"
            )

        if require_clean:
            self._ensure_no_unrelated_changes()

        return {
            "valid": True,
            "repo_path": str(self.repo_path),
            "remote": self.remote,
            "remote_url": remote_url,
            "branch": current_branch,
            "clean": self.is_clean(),
        }

    def preview_pull(self) -> dict[str, str]:
        self.validate(require_clean=False)
        output = self._fetch()
        local = self._git("rev-parse", "HEAD").strip()
        remote = self._git("rev-parse", f"{self.remote}/{self.branch}").strip()
        merge_base = self._git("merge-base", "HEAD", f"{self.remote}/{self.branch}").strip()
        return {"fetch": output, "local": local, "remote": remote, "merge_base": merge_base}

    def pull_ff_only(self) -> str:
        self.validate(require_clean=True)
        return self._pull()

    def commit_and_push_payload(self, revision_id: str) -> str:
        self.validate(require_clean=False)
        self._ensure_no_unrelated_changes()
        self._git("add", PAYLOAD_DIR_NAME)
        if not self._git("status", "--porcelain", "--", PAYLOAD_DIR_NAME).strip():
            return "No sync payload changes to push."
        self._git("commit", "-m", f"sync: update suzent brain {revision_id}")
        return self._push()

    def is_clean(self) -> bool:
        return not self._git("status", "--porcelain").strip()

    def _ensure_no_unrelated_changes(self) -> None:
        status = self._git("status", "--porcelain")
        unrelated = [
            line
            for line in status.splitlines()
            if not _status_path(line).startswith(f"{PAYLOAD_DIR_NAME}/")
        ]
        if unrelated:
            raise ValueError("Repository has unrelated changes outside the sync payload")

    def _remote_url(self) -> str:
        return self._git("remote", "get-url", self.remote).strip()

    def _fetch(self) -> str:
        token = resolve_github_token()
        remote_url = self._remote_url()
        if token and "github.com" in remote_url:
            return git_fetch_with_token(
                self.repo_path,
                token,
                authed_remote_for_push(remote_url, token),
                self.branch,
            )
        return self._git("fetch", self.remote, self.branch)

    def _pull(self) -> str:
        token = resolve_github_token()
        remote_url = self._remote_url()
        if token and "github.com" in remote_url:
            return git_pull_with_token(
                self.repo_path,
                token,
                authed_remote_for_push(remote_url, token),
                self.branch,
            )
        return self._git("pull", "--ff-only", self.remote, self.branch)

    def _push(self) -> str:
        token = resolve_github_token()
        remote_url = self._remote_url()
        if token and "github.com" in remote_url:
            return git_push_with_token(
                self.repo_path,
                token,
                authed_remote_for_push(remote_url, token),
                self.branch,
            )
        return self._git("push", self.remote, self.branch)

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
        return completed.stdout


def _status_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    return value.strip().replace("\\", "/")
