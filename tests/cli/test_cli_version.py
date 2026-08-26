"""Unit tests for `suzent --version`."""

import importlib
import subprocess
import sys

import pytest
from typer.testing import CliRunner

cli = importlib.import_module("suzent.cli")
cli_main = importlib.import_module("suzent.cli.main")
runner = CliRunner()


def _write_checkout(root, backend="0.4.2", ui="v0.4.1"):
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "suzent"\nversion = "{backend}"\n', encoding="utf-8"
    )
    if ui is not None:
        (root / "bin").mkdir(exist_ok=True)
        (root / "bin" / "version.txt").write_text(ui, encoding="utf-8")
    return root


def test_version_flag_reports_backend_and_ui(monkeypatch, tmp_path):
    _write_checkout(tmp_path)
    monkeypatch.setattr(cli, "get_project_root", lambda: tmp_path)

    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert "suzent 0.4.2 (ui 0.4.1)" in result.stdout


def test_short_version_flag_matches_long_flag(monkeypatch, tmp_path):
    _write_checkout(tmp_path)
    monkeypatch.setattr(cli, "get_project_root", lambda: tmp_path)

    assert (
        runner.invoke(cli.app, ["-V"]).stdout
        == runner.invoke(cli.app, ["--version"]).stdout
    )


def test_version_flag_does_not_require_a_subcommand(monkeypatch, tmp_path):
    _write_checkout(tmp_path)
    monkeypatch.setattr(cli, "get_project_root", lambda: tmp_path)

    result = runner.invoke(cli.app, ["--version"])

    assert "Missing command" not in result.stdout


def test_version_line_omits_ui_when_no_managed_binary(tmp_path):
    _write_checkout(tmp_path, ui=None)

    assert cli_main.format_version_line(tmp_path) == "suzent 0.4.2"


def test_version_line_falls_back_to_package_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "version", lambda name: "9.9.9")

    assert cli_main.format_version_line(tmp_path) == "suzent 9.9.9"


def test_version_line_reports_unknown_when_version_is_undiscoverable(
    monkeypatch, tmp_path
):
    def _missing(name):
        raise cli_main.PackageNotFoundError(name)

    monkeypatch.setattr(cli_main, "version", _missing)

    assert cli_main.format_version_line(tmp_path) == "suzent unknown"


@pytest.mark.parametrize("marker", ["latest", "v", "main"])
def test_version_line_reports_unknown_for_an_unresolved_ui_marker(tmp_path, marker):
    """`setup.sh` records the literal "latest" for dev and branch installs."""
    _write_checkout(tmp_path, ui=marker)

    assert cli_main.format_version_line(tmp_path) == "suzent 0.4.2 (ui unknown)"


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
