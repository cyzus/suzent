"""Exercise development update safety against real local Git repositories."""

import importlib
import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

cli = importlib.import_module("suzent.cli.main")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=root,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


@pytest.mark.parametrize(
    "state",
    ["clean", "dirty", "untracked", "detached", "no_upstream", "diverged", "merge"],
)
def test_development_update_preserves_checkout(
    monkeypatch, tmp_path: Path, state: str
) -> None:
    remote = tmp_path / "remote"
    remote.mkdir()
    git(remote, "init", "-b", "custom")
    (remote / "tracked.txt").write_text("original\n")
    git(remote, "add", ".")
    git(remote, "commit", "-m", "initial")
    checkout = tmp_path / "checkout"
    git(tmp_path, "clone", str(remote), str(checkout))
    old_head = git(checkout, "rev-parse", "HEAD")
    (remote / "remote.txt").write_text("upstream change\n")
    git(remote, "add", ".")
    git(remote, "commit", "-m", "upstream")
    target = git(remote, "rev-parse", "HEAD")
    if state == "dirty":
        (checkout / "tracked.txt").write_text("personal changes\n")
    elif state == "untracked":
        (checkout / "personal.txt").write_text("keep me\n")
    elif state == "detached":
        git(checkout, "checkout", "--detach")
    elif state == "no_upstream":
        git(checkout, "branch", "--unset-upstream")
    elif state == "diverged":
        (checkout / "local.txt").write_text("local commit\n")
        git(checkout, "add", ".")
        git(checkout, "commit", "-m", "local")
        old_head = git(checkout, "rev-parse", "HEAD")
    elif state == "merge":
        (checkout / ".git" / "MERGE_HEAD").write_text(old_head + "\n")
    old_status = git(checkout, "status", "--porcelain")
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> None:
        calls.append(command)
        if command[0] == "git":
            git(checkout, *command[1:])

    monkeypatch.setattr(cli, "get_project_root", lambda: checkout)
    monkeypatch.setattr(cli, "IS_WINDOWS", False)
    monkeypatch.setattr(cli, "run_command", run)
    monkeypatch.setattr(cli, "_rebuild_development_ui", lambda root: None)
    monkeypatch.setattr(cli, "_refresh_shortcuts", lambda root: None)
    app = typer.Typer()
    cli.register_commands(app)
    result = CliRunner().invoke(app, ["update", "--dev"])

    assert result.exit_code == (0 if state == "clean" else 1), result.output
    assert git(checkout, "rev-parse", "HEAD") == (
        target if state == "clean" else old_head
    )
    assert git(checkout, "branch", "--show-current") == (
        "" if state == "detached" else "custom"
    )
    assert git(checkout, "stash", "list") == ""
    if state != "clean":
        assert git(checkout, "status", "--porcelain") == old_status
        assert not any(command[0] in {"uv", "npm"} for command in calls)
    if state == "dirty":
        assert (checkout / "tracked.txt").read_text() == "personal changes\n"
    if state == "untracked":
        assert (checkout / "personal.txt").read_text() == "keep me\n"
