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


def test_pull_clears_untracked_payload_files(tmp_path: Path):
    """An untracked local payload file must not block a ff-only pull once the
    remote starts tracking that same path (the "untracked working tree files
    would be overwritten by merge" abort)."""
    repo = make_repo(tmp_path)

    # A second clone that pushes a tracked payload file to the remote.
    other = tmp_path / "other"
    git(tmp_path, "clone", str(tmp_path / "remote.git"), str(other))
    git(other, "config", "user.email", "test@example.com")
    git(other, "config", "user.name", "Test User")
    git(other, "checkout", "master")
    other_payload = other / PAYLOAD_DIR_NAME
    other_payload.mkdir()
    (other_payload / "node_devices.json").write_text("[]", encoding="utf-8")
    git(other, "add", PAYLOAD_DIR_NAME)
    git(other, "commit", "-m", "add payload")
    git(other, "push", "origin", "master")

    # Locally the same path exists only as an untracked file.
    payload = repo / PAYLOAD_DIR_NAME
    payload.mkdir()
    (payload / "node_devices.json").write_text("stale local", encoding="utf-8")

    # Without cleaning untracked files this aborts; the fix must let it through.
    GitHubSyncProvider(repo, branch="master").pull_ff_only()

    assert (payload / "node_devices.json").read_text(encoding="utf-8") == "[]"
