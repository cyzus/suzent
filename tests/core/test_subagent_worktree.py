import subprocess
from pathlib import Path

import pytest

from suzent.core.subagent_runner import (
    SubAgentTask,
    _setup_worktree,
    _teardown_worktree,
)


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git("init", "-q", cwd=tmp_path)
    _git("config", "user.email", "test@example.com", cwd=tmp_path)
    _git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("hello\n")
    _git("add", ".", cwd=tmp_path)
    _git("commit", "-q", "-m", "init", cwd=tmp_path)
    return tmp_path


async def _worktree_task(repo: Path, task_id: str) -> SubAgentTask:
    task = SubAgentTask(
        task_id=task_id,
        parent_chat_id="parent",
        description="test",
        tools_allowed=[],
        isolation="worktree",
        isolation_target_path=str(repo),
    )
    assert await _setup_worktree(task) is None
    return task


async def test_untouched_worktree_is_removed(repo: Path) -> None:
    task = await _worktree_task(repo, "clean")
    path, branch = task.worktree_path, task.worktree_branch

    await _teardown_worktree(task)

    assert not Path(path).exists()
    assert _git("branch", "--list", branch, cwd=repo) == ""
    assert task.worktree_path is None and task.worktree_branch is None


async def test_uncommitted_changes_keep_the_worktree(repo: Path) -> None:
    task = await _worktree_task(repo, "dirty")
    path = task.worktree_path
    (Path(path) / "new.txt").write_text("work\n")

    await _teardown_worktree(task)

    assert (Path(path) / "new.txt").read_text() == "work\n"
    assert task.worktree_path == path


async def test_commits_keep_the_branch(repo: Path) -> None:
    task = await _worktree_task(repo, "committed")
    path, branch = task.worktree_path, task.worktree_branch
    (Path(path) / "new.txt").write_text("work\n")
    _git("add", ".", cwd=Path(path))
    _git("commit", "-q", "-m", "work", cwd=Path(path))

    await _teardown_worktree(task)

    assert _git("branch", "--list", branch, cwd=repo) != ""
    assert task.worktree_branch == branch
