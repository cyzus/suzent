"""Unit tests for `suzent --version`."""

import importlib
import subprocess
import sys

import pytest
from typer.testing import CliRunner

cli = importlib.import_module("suzent.cli")
cli_main = importlib.import_module("suzent.cli.main")
runner = CliRunner()

_COMMIT = "1234abcd5678ef901234abcd5678ef901234abcd"


def _write_checkout(root, backend="0.4.2", ui="v0.4.1", channel="stable"):
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "suzent"\nversion = "{backend}"\n', encoding="utf-8"
    )
    if ui is not None:
        (root / "bin").mkdir(exist_ok=True)
        (root / "bin" / "version.txt").write_text(ui, encoding="utf-8")
    if channel is not None:
        (root / ".suzent").mkdir(exist_ok=True)
        (root / ".suzent" / "update-channel").write_text(channel, encoding="utf-8")
    return root


@pytest.fixture
def known_commit(monkeypatch):
    """Pin the commit: it resolves from the real checkout, not the tmp root."""
    monkeypatch.setattr(cli_main, "get_backend_commit", lambda: _COMMIT)


@pytest.fixture
def no_commit(monkeypatch):
    monkeypatch.setattr(cli_main, "get_backend_commit", lambda: cli_main.UNKNOWN)


def test_version_flag_reports_backend_commit_and_ui(
    monkeypatch, tmp_path, known_commit
):
    _write_checkout(tmp_path)
    monkeypatch.setattr(cli, "get_project_root", lambda: tmp_path)

    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert "suzent 0.4.2 (1234abcd, ui 0.4.1)" in result.stdout


def test_short_version_flag_matches_long_flag(monkeypatch, tmp_path, known_commit):
    _write_checkout(tmp_path)
    monkeypatch.setattr(cli, "get_project_root", lambda: tmp_path)

    assert (
        runner.invoke(cli.app, ["-V"]).stdout
        == runner.invoke(cli.app, ["--version"]).stdout
    )


def test_version_flag_does_not_require_a_subcommand(
    monkeypatch, tmp_path, known_commit
):
    _write_checkout(tmp_path)
    monkeypatch.setattr(cli, "get_project_root", lambda: tmp_path)

    assert "Missing command" not in runner.invoke(cli.app, ["--version"]).stdout


def test_dev_channel_is_named_instead_of_the_unused_ui_binary(tmp_path, known_commit):
    """`start` builds the UI from source on the dev channel, so its tag is noise."""
    _write_checkout(tmp_path, ui="latest", channel="dev")

    assert cli_main.format_version_line(tmp_path) == "suzent 0.4.2 (1234abcd, dev)"


def test_version_line_omits_ui_when_no_managed_binary(tmp_path, known_commit):
    _write_checkout(tmp_path, ui=None)

    assert cli_main.format_version_line(tmp_path) == "suzent 0.4.2 (1234abcd)"


def test_version_line_carries_only_the_version_without_git_or_ui(tmp_path, no_commit):
    _write_checkout(tmp_path, ui=None)

    assert cli_main.format_version_line(tmp_path) == "suzent 0.4.2"


@pytest.mark.parametrize("marker", ["latest", "v", "main"])
def test_version_line_reports_unknown_for_an_unresolved_ui_marker(
    tmp_path, marker, known_commit
):
    """`setup.sh` records the literal "latest" for dev and branch installs."""
    _write_checkout(tmp_path, ui=marker)

    assert cli_main.format_version_line(tmp_path) == (
        "suzent 0.4.2 (1234abcd, ui unknown)"
    )


def test_version_line_falls_back_to_package_metadata(monkeypatch, tmp_path, no_commit):
    monkeypatch.setattr(cli_main, "version", lambda name: "9.9.9")

    assert cli_main.format_version_line(tmp_path) == "suzent 9.9.9"


def test_version_line_reports_unknown_when_version_is_undiscoverable(
    monkeypatch, tmp_path, no_commit
):
    def _missing(name):
        raise cli_main.PackageNotFoundError(name)

    monkeypatch.setattr(cli_main, "version", _missing)

    assert cli_main.format_version_line(tmp_path) == "suzent unknown"


def test_version_writes_nothing_to_stderr():
    """Regression: config logged its override file before logging was configured."""
    result = subprocess.run(
        [sys.executable, "-m", "suzent.cli", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stderr == ""
    assert len(result.stdout.strip().splitlines()) == 1
    assert result.stdout.startswith("suzent ")
