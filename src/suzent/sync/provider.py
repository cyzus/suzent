from __future__ import annotations

from pathlib import Path

from suzent.logger import get_logger
from suzent.sync.git_transport import is_github_https_url, run_git
from suzent.sync.github_api import resolve_github_token
from suzent.sync.payload import PAYLOAD_DIR_NAME

logger = get_logger(__name__)


class SyncConflictError(RuntimeError):
    """Local and remote payload commits touch the same files and cannot be rebased."""


class GitHubSyncProvider:
    def __init__(
        self, repo_path: Path, *, remote: str = "origin", branch: str = "main"
    ):
        self.repo_path = repo_path.expanduser().resolve()
        self.remote = remote
        self.branch = branch
        self._token: str | None = None
        self._token_resolved = False

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

    def refresh_remote(self) -> None:
        self.validate(require_clean=False)
        self._fetch()

    def payload_diff_name_status(self, left_ref: str, right_ref: str) -> str:
        self.validate(require_clean=False)
        return self._git(
            "diff", "--name-status", left_ref, right_ref, "--", PAYLOAD_DIR_NAME
        )

    def payload_file_diff_patch(self, left_ref: str, right_ref: str, path: str) -> str:
        normalized = path.replace("\\", "/").removeprefix(f"{PAYLOAD_DIR_NAME}/")
        self.validate(require_clean=False)
        return self._git(
            "diff",
            "--no-ext-diff",
            "--unified=3",
            left_ref,
            right_ref,
            "--",
            f"{PAYLOAD_DIR_NAME}/{normalized}",
        )

    def discard_payload_changes(self) -> None:
        self._discard_payload_changes()

    def discard_payload_paths(self, paths: list[str]) -> None:
        payload_paths = [
            f"{PAYLOAD_DIR_NAME}/{path.replace('\\', '/').removeprefix(f'{PAYLOAD_DIR_NAME}/')}"
            for path in paths
        ]
        if not payload_paths:
            return
        try:
            self._git("checkout", "--", *payload_paths)
        except RuntimeError:
            pass
        try:
            self._git("clean", "-f", "--", *payload_paths)
        except RuntimeError:
            pass

    def pull_ff_only(self) -> str:
        self._discard_payload_changes()
        self.validate(require_clean=False)
        try:
            return self._pull()
        except RuntimeError as exc:
            if (
                "Not possible to fast-forward" not in str(exc)
                and "diverging" not in str(exc).lower()
            ):
                raise
            logger.info("ff-only pull failed (diverged) — rebasing local onto remote")
        self._fetch()
        remote_ref = f"{self.remote}/{self.branch}"
        self._rebase_onto(remote_ref)
        return f"Rebased onto {remote_ref}"

    def _discard_payload_changes(self) -> None:
        """Discard any uncommitted changes inside the payload directory before pulling.

        The payload is always regenerated on push, so local dirty state is safe to
        drop. This covers both tracked edits (``checkout``) and *untracked* files
        (``clean``): once the remote starts tracking a payload path that only
        exists locally as an untracked file, a ff-only pull aborts with "untracked
        working tree files would be overwritten by merge" unless we clear it first.
        """
        try:
            self._git("checkout", "--", PAYLOAD_DIR_NAME)
        except RuntimeError:
            pass  # no changes or directory doesn't exist yet — fine either way
        try:
            self._git("clean", "-fd", "--", PAYLOAD_DIR_NAME)
        except RuntimeError:
            pass  # nothing untracked to clean — fine either way

    def commit_and_push_payload(self) -> str:
        base = self.head()
        if not self.commit_payload():
            return "No sync payload changes to push."
        try:
            return self.push_payload()
        except SyncConflictError:
            # Drop our commit so the payload matches the last synced state again.
            # The live files still hold the local edits, so the next plan shows
            # them as outgoing next to the conflicting incoming files.
            self.reset_hard(base)
            raise

    def commit_payload(self) -> bool:
        """Commit the payload directory locally. Returns False if nothing changed."""
        self.validate(require_clean=False)
        self._git("add", PAYLOAD_DIR_NAME)
        self._ensure_no_unrelated_staged_changes()
        staged = self._git("status", "--porcelain", "--", PAYLOAD_DIR_NAME).strip()
        if not staged:
            return False
        self._git("commit", "-m", "sync: update portable files")
        return True

    def push_payload(self) -> str:
        return self._push_with_rebase()

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

    def reset_hard(self, ref: str) -> None:
        self._git("reset", "--hard", ref)

    def is_clean(self) -> bool:
        return not self._git("status", "--porcelain").strip()

    def _ensure_no_unrelated_staged_changes(self) -> None:
        """Fail if anything outside the payload dir is staged (would contaminate the commit)."""
        staged_files = self._git("diff", "--cached", "--name-only").splitlines()
        unrelated = [
            f
            for f in staged_files
            if not f.replace("\\", "/").startswith(f"{PAYLOAD_DIR_NAME}/")
        ]
        if unrelated:
            raise ValueError("Repository has staged changes outside the sync payload")

    def _remote_url(self) -> str:
        return self._git("remote", "get-url", self.remote).strip()

    def _fetch(self) -> str:
        return self._git_remote("fetch", self.remote, self.branch)

    def _pull(self) -> str:
        return self._git_remote("pull", "--ff-only", self.remote, self.branch)

    def _push(self) -> str:
        return self._git_remote("push", self.remote, self.branch)

    def _git_remote(self, *args: str) -> str:
        """Run a git command that talks to the remote, authenticated if GitHub."""
        token = (
            self._github_token() if is_github_https_url(self._remote_url()) else None
        )
        return run_git(self.repo_path, *args, token=token)

    def _github_token(self) -> str | None:
        # Resolve once per provider (one sync operation): resolving may refresh
        # the token over HTTP, and a sync makes several remote calls.
        if not self._token_resolved:
            self._token = resolve_github_token()
            self._token_resolved = True
        return self._token

    def _rebase_onto(self, remote_ref: str) -> None:
        """Rebase current branch onto remote_ref, raising SyncConflictError on conflict.

        Never hard-reset to the remote here: that silently drops the local
        commit, and a following apply would overwrite the live files with the
        remote version.
        """
        try:
            self._git("rebase", remote_ref)
        except RuntimeError as exc:
            try:
                self._git("rebase", "--abort")
            except RuntimeError:
                pass
            raise SyncConflictError(
                f"Local and remote sync changes conflict on {remote_ref}"
            ) from exc

    def _push_with_rebase(self) -> str:
        """Push, rebasing on top of any remote commits that arrived since we committed."""
        try:
            return self._push()
        except RuntimeError as exc:
            if "non-fast-forward" not in str(exc) and "rejected" not in str(exc):
                raise
            logger.info("Push rejected (non-fast-forward) — fetching and rebasing")

        self._fetch()
        self._rebase_onto(f"{self.remote}/{self.branch}")
        return self._push()

    def _git(self, *args: str) -> str:
        return run_git(self.repo_path, *args)
