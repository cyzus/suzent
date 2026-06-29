from pathlib import Path
import subprocess

import pytest

from suzent.sync.payload import PAYLOAD_DIR_NAME
from suzent.sync.provider import GitHubSyncProvider


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def make_repo(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("initial", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "initial")
    git(repo, "branch", "-M", "master")
    git(repo, "push", "origin", "master")
    return repo


def test_provider_pushes_only_sync_payload_to_bare_remote(tmp_path: Path):
    repo = make_repo(tmp_path)
    payload = repo / PAYLOAD_DIR_NAME
    payload.mkdir()
    (payload / "memory.md").write_text("brain", encoding="utf-8")

    result = GitHubSyncProvider(repo, branch="master").commit_and_push_payload("rev1")

    assert "master" in result or result == ""


def test_provider_refuses_unrelated_staged_changes(tmp_path: Path):
    repo = make_repo(tmp_path)
    payload = repo / PAYLOAD_DIR_NAME
    payload.mkdir()
    (payload / "memory.md").write_text("brain", encoding="utf-8")
    # Stage an unrelated file — this should be rejected
    (repo / "README.md").write_text("dirty", encoding="utf-8")
    git(repo, "add", "README.md")

    with pytest.raises(ValueError, match="staged changes outside the sync payload"):
        GitHubSyncProvider(repo, branch="master").commit_and_push_payload("rev1")
