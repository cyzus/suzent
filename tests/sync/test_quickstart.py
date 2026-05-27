import subprocess
from pathlib import Path

import pytest

from suzent.sync import quickstart as quickstart_module
from suzent.sync.quickstart import (
    normalize_repo_name,
    quickstart_github_sync,
)


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


def test_normalize_repo_name():
    assert normalize_repo_name("My-Brain") == "my-brain"


def test_quickstart_raises_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "github-sync"
    monkeypatch.setattr(quickstart_module, "DEFAULT_REPO_DIR", repo)
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(
        quickstart_module, "resolve_github_token", lambda value=None: None
    )

    with pytest.raises(ValueError, match="Sign in with GitHub first"):
        quickstart_github_sync()


def test_quickstart_initializes_local_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "github-sync"
    monkeypatch.setattr(quickstart_module, "DEFAULT_REPO_DIR", repo)
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        quickstart_module, "resolve_github_token", lambda value=None: "fake-token"
    )
    monkeypatch.setattr(
        quickstart_module, "get_authenticated_user", lambda token: "alice"
    )
    monkeypatch.setattr(
        quickstart_module,
        "_remote_repo_exists",
        lambda token, username, repo_name: False,
    )
    monkeypatch.setattr(
        quickstart_module, "_create_github_repo_api", lambda *a, **kw: (None, False)
    )

    result = quickstart_github_sync()

    assert result["success"] is True
    assert (repo / ".git").exists()
    assert result["repo_name"] == "suzent-brain"


def test_quickstart_custom_repo_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "github-sync"
    monkeypatch.setattr(quickstart_module, "DEFAULT_REPO_DIR", repo)
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        quickstart_module, "resolve_github_token", lambda value=None: "fake-token"
    )
    monkeypatch.setattr(
        quickstart_module, "get_authenticated_user", lambda token: "alice"
    )
    monkeypatch.setattr(
        quickstart_module,
        "_remote_repo_exists",
        lambda token, username, repo_name: False,
    )
    monkeypatch.setattr(
        quickstart_module, "_create_github_repo_api", lambda *a, **kw: (None, False)
    )

    result = quickstart_github_sync(repo_name="custom-brain")

    assert result["repo_name"] == "custom-brain"


def test_quickstart_uses_custom_remote_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "custom-sync"
    monkeypatch.setattr(
        quickstart_module, "resolve_github_token", lambda value=None: "fake-token"
    )
    monkeypatch.setattr(
        quickstart_module, "get_authenticated_user", lambda token: "alice"
    )
    monkeypatch.setattr(
        quickstart_module,
        "_remote_repo_exists",
        lambda token, username, repo_name: False,
    )
    monkeypatch.setattr(
        quickstart_module, "_create_github_repo_api", lambda *a, **kw: (None, False)
    )

    result = quickstart_github_sync(
        repo_name="alice/custom-brain",
        repo_path=repo,
        remote="upstream",
    )

    assert result["remote"] == "upstream"
    assert quickstart_module._git_in(repo, "remote", "get-url", "upstream").strip() == (
        "https://github.com/alice/custom-brain.git"
    )
    with pytest.raises(RuntimeError):
        quickstart_module._git_in(repo, "remote", "get-url", "origin")


def test_quickstart_clones_existing_remote_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source"
    remote = tmp_path / "remote.git"
    target = tmp_path / "fresh-sync"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(source))
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test User")
    (source / "README.md").write_text("remote history", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "seed remote")
    git(source, "push", "origin", "master")

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(
        quickstart_module, "resolve_github_token", lambda value=None: "fake-token"
    )
    monkeypatch.setattr(
        quickstart_module, "get_authenticated_user", lambda token: "alice"
    )
    monkeypatch.setattr(
        quickstart_module,
        "public_clone_url",
        lambda username, repo_name: str(remote),
    )
    monkeypatch.setattr(
        quickstart_module,
        "_remote_repo_exists",
        lambda token, username, repo_name: True,
    )
    monkeypatch.setattr(
        quickstart_module,
        "authed_clone_url",
        lambda owner, repo, token: str(remote),
    )

    result = quickstart_github_sync(
        repo_name="alice/custom-brain",
        repo_path=target,
    )

    assert result["success"] is True
    assert (target / ".git").exists()
    assert (target / "README.md").read_text(encoding="utf-8") == "remote history"
    assert "Created initial commit" not in result["actions"]
