import importlib
import subprocess
from pathlib import Path

import pytest

cli = importlib.import_module("suzent.cli.main")


@pytest.mark.parametrize("failure", [None, "build", "missing", "install"])
def test_development_desktop_replaces_both_targets_or_restores_old(
    monkeypatch, tmp_path: Path, failure: str | None
) -> None:
    monkeypatch.setattr(cli, "IS_WINDOWS", False)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="suzent"\nversion="1.2.3"\n'
    )
    binary = tmp_path / "src-tauri/target/release/suzent"
    managed = tmp_path / "bin/suzent-ui"
    for path in (binary, managed):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")
    (managed.parent / "version.txt").write_text("v1.2.2")

    def build(command: list[str], **kwargs: object) -> None:
        assert command == ["npm", "run", "build:dist", "--", "--no-bundle"]
        assert kwargs["env"]["CARGO_TARGET_DIR"] == str(binary.parent.parent.resolve())
        assert not binary.exists()
        if failure == "missing":
            return
        binary.write_bytes(b"new")
        if failure == "build":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(cli, "run_command", build)
    if failure == "install":

        def fail_install(*args: object) -> None:
            raise OSError("locked")

        monkeypatch.setattr(cli, "_replace_ui_files", fail_install)
    if failure:
        with pytest.raises((OSError, subprocess.CalledProcessError)):
            cli._rebuild_development_ui(tmp_path)
        assert binary.read_bytes() == managed.read_bytes() == b"old"
        assert (managed.parent / "version.txt").read_text() == "v1.2.2"
    else:
        cli._rebuild_development_ui(tmp_path)
        assert binary.read_bytes() == managed.read_bytes() == b"new"
        assert (managed.parent / "version.txt").read_text() == "v1.2.3"
