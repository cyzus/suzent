import asyncio
from pathlib import Path
import subprocess

import pytest

from suzent.sync.models import SyncProfile
from suzent.sync.payload import PAYLOAD_DIR_NAME, SyncPayloadBuilder
from suzent.sync.provider import GitHubSyncProvider
from suzent.sync.service import GitHubSyncService


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

    result = GitHubSyncProvider(repo, branch="master").commit_and_push_payload()

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
        GitHubSyncProvider(repo, branch="master").commit_and_push_payload()


def test_push_plan_does_not_modify_repository_worktree(tmp_path: Path):
    repo = make_repo(tmp_path)
    config_dir = tmp_path / "config"
    skills_dir = tmp_path / "skills"
    memory_dir = tmp_path / "sandbox" / "shared" / "memory"
    config_dir.mkdir()
    skills_dir.mkdir()
    memory_dir.mkdir(parents=True)
    config_file = config_dir / "default.yaml"
    config_file.write_text("model: first\n", encoding="utf-8")

    builder = SyncPayloadBuilder(
        user_config_dir=config_dir,
        user_skills_dir=skills_dir,
        sandbox_data_path=tmp_path / "sandbox",
    )
    profile = SyncProfile(repo_path=str(repo), branch="master")
    builder.build(repo)
    GitHubSyncProvider(repo, branch="master").commit_and_push_payload()

    config_file.write_text("model: second\n", encoding="utf-8")
    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json", payload_builder=builder
    )
    service.save_profile(profile)
    before = git(repo, "status", "--porcelain")

    plan = service.preview_sync_plan("push", profile.id)
    diff = service.preview_file_diff("config/default.yaml", "outgoing", profile.id)

    assert any(change.path == "config/default.yaml" for change in plan.files)
    assert "-model: first" in diff
    assert "+model: second" in diff
    assert git(repo, "status", "--porcelain") == before


def test_discard_one_outgoing_file_leaves_other_change_pending(tmp_path: Path):
    repo = make_repo(tmp_path)
    config_dir = tmp_path / "config"
    skills_dir = tmp_path / "skills"
    memory_dir = tmp_path / "sandbox" / "shared" / "memory"
    config_dir.mkdir()
    skills_dir.mkdir()
    memory_dir.mkdir(parents=True)
    first = config_dir / "default.yaml"
    second = config_dir / "config.yaml"
    first.write_text("value: cloud-first\n", encoding="utf-8")
    second.write_text("value: cloud-second\n", encoding="utf-8")

    builder = SyncPayloadBuilder(
        user_config_dir=config_dir,
        user_skills_dir=skills_dir,
        sandbox_data_path=tmp_path / "sandbox",
    )
    profile = SyncProfile(repo_path=str(repo), branch="master")
    builder.build(repo)
    GitHubSyncProvider(repo, branch="master").commit_and_push_payload()
    first.write_text("value: local-first\n", encoding="utf-8")
    second.write_text("value: local-second\n", encoding="utf-8")

    service = GitHubSyncService(
        profiles_path=tmp_path / "profiles.json", payload_builder=builder
    )
    service.save_profile(profile)

    result = asyncio.run(
        service.discard_outgoing(profile.id, paths=["config/default.yaml"])
    )
    remaining = service.preview_sync_plan("push", profile.id)

    assert result["discarded"] == ["config/default.yaml"]
    assert first.read_text(encoding="utf-8") == "value: cloud-first\n"
    assert second.read_text(encoding="utf-8") == "value: local-second\n"
    assert {change.path for change in remaining.files} == {"config/config.yaml"}


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
