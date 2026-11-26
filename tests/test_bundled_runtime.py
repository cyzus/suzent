import sys
from pathlib import Path

import pytest

from suzent.config import paths
from suzent.version import get_runtime_kind


def _install(tmp_path: Path) -> tuple[Path, Path]:
    prefix = tmp_path / "resources" / "runtime" / "python"
    prefix.mkdir(parents=True)
    resources = tmp_path / "resources" / "suzent"
    resources.mkdir()
    (resources / "bundle.json").write_text('{"version": "1.0.0"}')
    return prefix, resources


def test_bundled_runtime_finds_its_resources_without_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix, resources = _install(tmp_path)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.delenv("SUZENT_PROJECT_DIR", raising=False)
    monkeypatch.delenv("SUZENT_PACKAGED", raising=False)
    assert paths.bundled_resources_dir() == resources.resolve()
    assert paths.get_project_root() == resources.resolve()
    assert get_runtime_kind() == "bundled"


def test_an_ordinary_python_is_not_bundled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "venv"))
    assert paths.bundled_resources_dir() is None


def test_explicit_project_dir_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix, _ = _install(tmp_path)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setenv("SUZENT_PROJECT_DIR", str(tmp_path / "elsewhere"))
    assert paths.get_project_root() == (tmp_path / "elsewhere").resolve()


def test_a_copy_installed_below_a_checkout_is_not_a_source_run(tmp_path: Path) -> None:
    from suzent.version import get_backend_source_root

    checkout = tmp_path / "repo"
    (checkout / "src" / "suzent").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "suzent"\nversion = "1.0.0"\n'
    )
    installed = checkout / "build" / "site-packages" / "suzent" / "version.py"
    installed.parent.mkdir(parents=True)
    installed.touch()
    source = checkout / "src" / "suzent" / "version.py"
    source.touch()
    assert get_backend_source_root(installed) is None
    assert get_backend_source_root(source) == checkout.resolve()


def test_update_commands_refuse_in_bundled_install(monkeypatch):
    from typer.testing import CliRunner

    from suzent.cli import app

    monkeypatch.setenv("SUZENT_PACKAGED", "1")
    runner = CliRunner()
    for command in ("update", "upgrade", "repair"):
        result = runner.invoke(app, [command])
        assert result.exit_code == 1, command
        assert "updates itself" in result.output
