from __future__ import annotations

import subprocess
from pathlib import Path

from suzent.core.git_status import (
    discover_chat_git_repositories,
    get_chat_git_status,
    inspect_git_repository,
)


def _init_git_repo(path: Path, branch: str = "main") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", branch], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_inspect_git_repository_tracks_clean_and_dirty_states(tmp_path: Path) -> None:
    repo = tmp_path / "alpha"
    _init_git_repo(repo, branch="feat/status")
    tracked = repo / "hello.txt"
    tracked.write_text("line1\nline2\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "hello.txt"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True
    )

    clean = inspect_git_repository(repo, primary=True)
    assert clean is not None
    assert clean["name"] == "alpha"
    assert clean["branch"] == "feat/status"
    assert clean["primary"] is True
    assert clean["clean"] is True
    assert clean["total_changed"] == 0

    tracked.write_text("line1\nline2-modified\nline3\n", encoding="utf-8")
    (repo / "new_file.py").write_text("print(1)\n", encoding="utf-8")

    dirty = inspect_git_repository(repo, primary=True)
    assert dirty is not None
    assert dirty["clean"] is False
    assert dirty["modified"] == 1
    assert dirty["untracked"] == 1
    assert dirty["additions"] == 2
    assert dirty["deletions"] == 1
    assert dirty["total_changed"] == 2
    paths = {item["path"]: item["status"] for item in dirty["files"]}
    assert paths == {"hello.txt": "M", "new_file.py": "?"}

    # Stage hello.txt and modify it again so it has both staged and unstaged changes (MM).
    # total_changed must still count hello.txt only once.
    subprocess.run(
        ["git", "add", "hello.txt"], cwd=repo, check=True, capture_output=True
    )
    tracked.write_text(
        "line1\nline2-modified\nline3\nline4-unstaged\n", encoding="utf-8"
    )
    both_staged_and_modified = inspect_git_repository(repo, primary=True)
    assert both_staged_and_modified is not None
    assert both_staged_and_modified["staged"] == 1
    assert both_staged_and_modified["modified"] == 1
    assert both_staged_and_modified["untracked"] == 1
    assert both_staged_and_modified["total_changed"] == 2
    assert len(both_staged_and_modified["files"]) == 2


def test_multi_repo_discovery_deduplicates_and_orders_primary_first(
    tmp_path: Path, monkeypatch
) -> None:
    repo_primary = tmp_path / "repo-primary"
    repo_extra = tmp_path / "repo-extra"
    _init_git_repo(repo_primary, branch="main")
    _init_git_repo(repo_extra, branch="dev")

    (repo_primary / "a.txt").write_text("a\n", encoding="utf-8")
    (repo_extra / "b.txt").write_text("b\n", encoding="utf-8")

    project_dir = tmp_path / "sandbox_project"
    project_dir.mkdir(parents=True, exist_ok=True)
    subdir = repo_primary / "packages" / "core"
    subdir.mkdir(parents=True, exist_ok=True)

    from suzent.core.repository_context import RepositoryContextRoots

    fake_roots = RepositoryContextRoots(
        project_dir=project_dir,
        working_dir=subdir,
        repository_root=repo_primary,
        home_dir=tmp_path,
        asset_directories=(repo_extra, subdir, repo_primary),
    )
    monkeypatch.setattr(
        "suzent.core.git_status.resolve_repository_context",
        lambda chat_id, cwd=None, custom_volumes=None: fake_roots,
    )

    discovered = discover_chat_git_repositories("chat-1")
    assert len(discovered) == 2
    assert discovered[0]["name"] == "repo-primary"
    assert discovered[0]["primary"] is True
    assert discovered[1]["name"] == "repo-extra"
    assert discovered[1]["primary"] is False

    status = get_chat_git_status("chat-1")
    assert len(status["repositories"]) == 2
    assert status["repositories"][0]["name"] == "repo-primary"
    assert status["repositories"][0]["branch"] == "main"
    assert status["repositories"][0]["untracked"] == 1
    assert status["repositories"][1]["name"] == "repo-extra"
    assert status["repositories"][1]["branch"] == "dev"
    assert status["repositories"][1]["untracked"] == 1


def test_excludes_suzent_project_dir_and_subdirectories(
    tmp_path: Path, monkeypatch
) -> None:
    suzent_home = tmp_path / ".suzent"
    project_dir = suzent_home / "sandbox" / "projects" / "default"
    scratch_repo = project_dir / "scratch" / "cloned-repo"
    _init_git_repo(project_dir, branch="main")
    _init_git_repo(scratch_repo, branch="main")

    user_repo = tmp_path / "workspace" / "my-app"
    _init_git_repo(user_repo, branch="feat/ui")

    from suzent.core.repository_context import RepositoryContextRoots

    fake_roots = RepositoryContextRoots(
        project_dir=project_dir,
        working_dir=project_dir / "scratch",
        repository_root=project_dir,
        home_dir=tmp_path,
        asset_directories=(project_dir / "scratch", scratch_repo, user_repo),
    )
    monkeypatch.setattr(
        "suzent.core.git_status.resolve_repository_context",
        lambda chat_id, cwd=None, custom_volumes=None: fake_roots,
    )

    discovered = discover_chat_git_repositories("chat-1")
    assert [item["name"] for item in discovered] == ["my-app"]
