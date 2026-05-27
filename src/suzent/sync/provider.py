from __future__ import annotations

import subprocess
from pathlib import Path

from suzent.logger import get_logger
from suzent.sync.github_api import resolve_github_token
from suzent.sync.github_token import (
    _redact_git_credentials,
    authed_remote_for_push,
    git_fetch_with_token,
    git_pull_with_token,
    git_push_with_token,
)
from suzent.sync.payload import PAYLOAD_DIR_NAME

logger = get_logger(__name__)


class GitHubSyncProvider:
    def __init__(
        self, repo_path: Path, *, remote: str = "origin", branch: str = "main"
    ):
        self.repo_path = repo_path.expanduser().resolve()
        self.remote = remote
        self.branch = branch

    def validate(self, *, require_clean: bool = False) -> dict[str, str | bool]:
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

        return {
            "valid": True,
            "repo_path": str(self.repo_path),
            "remote": self.remote,
            "remote_url": remote_url,
            "branch": current_branch,
            "clean": self.is_clean(),
        }

    def preview_pull(self) -> dict:
        self.validate(require_clean=False)
        output = self._fetch()
        local = self._git("rev-parse", "HEAD").strip()
        remote_ref = f"{self.remote}/{self.branch}"
        remote = self._git("rev-parse", remote_ref).strip()
        merge_base = self._git("merge-base", "HEAD", remote_ref).strip()
        ahead = len(self._git("rev-list", f"{remote_ref}..HEAD").splitlines())
        behind = len(self._git("rev-list", f"HEAD..{remote_ref}").splitlines())
        return {
            "fetch": output,
            "local": local,
            "remote": remote,
            "merge_base": merge_base,
            "ahead": ahead,
            "behind": behind,
        }

    def pull_ff_only(self) -> str:
        self._discard_payload_changes()
        self.validate(require_clean=False)
        return self._pull()

    def _discard_payload_changes(self) -> None:
        """Discard any uncommitted changes inside the payload directory before pulling.

        The payload is always regenerated on push, so local dirty state is safe to drop.
        """
        try:
            self._git("checkout", "--", PAYLOAD_DIR_NAME)
        except RuntimeError:
            pass  # no changes or directory doesn't exist yet — fine either way

    def commit_and_push_payload(self, revision_id: str) -> str:
        self.validate(require_clean=False)
        self._git("add", PAYLOAD_DIR_NAME)
        self._ensure_no_unrelated_staged_changes()
        staged = self._git("status", "--porcelain", "--", PAYLOAD_DIR_NAME).strip()
        if not staged:
            return "No sync payload changes to push."
        if _only_metadata_changed(staged):
            self._git("restore", "--staged", PAYLOAD_DIR_NAME)
            return "No meaningful changes to push (only manifest/presence updated)."
        self._git("commit", "-m", f"sync: update suzent brain {revision_id}")
        return self._push()

    def is_clean(self) -> bool:
        return not self._git("status", "--porcelain").strip()

    def _ensure_no_unrelated_staged_changes(self) -> None:
        """Fail if anything outside the payload dir is staged (would contaminate the commit)."""
        # --cached shows only staged changes; index status is the first character.
        status = self._git("status", "--porcelain", "--cached")
        unrelated = [
            line
            for line in status.splitlines()
            if not _status_path(line).startswith(f"{PAYLOAD_DIR_NAME}/")
        ]
        if unrelated:
            raise ValueError("Repository has staged changes outside the sync payload")

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
            detail = _redact_git_credentials(
                completed.stderr.strip() or completed.stdout.strip()
            )
            command = " ".join(_redact_git_credentials(arg) for arg in args)
            raise RuntimeError(f"git {command} failed: {detail}")
        return completed.stdout


def _status_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    return value.strip().replace("\\", "/")


# Paths that are always regenerated on every push and carry no meaningful content.
_METADATA_PREFIXES = (
    f"{PAYLOAD_DIR_NAME}/_sync/manifest.json",
    f"{PAYLOAD_DIR_NAME}/_sync/presence/",
)


def _only_metadata_changed(porcelain_output: str) -> bool:
    """Return True if every staged change is a manifest or presence file."""
    for line in porcelain_output.splitlines():
        path = _status_path(line).replace("\\", "/")
        if not any(path.startswith(p) for p in _METADATA_PREFIXES):
            return False
    return True
