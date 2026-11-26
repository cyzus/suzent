import importlib
import subprocess
from pathlib import Path

import pytest

cli = importlib.import_module("suzent.cli.main")


def _write_build(root: Path, label: str) -> None:
    electron = root / "apps/desktop/node_modules/electron"
    (electron / "dist").mkdir(parents=True, exist_ok=True)
    (electron / "path.txt").write_text("electron")
    (electron / "dist/electron").write_bytes(b"exe")
    for output, name in (
        (root / "apps/desktop/dist", "main.js"),
        (root / "frontend/dist", "index.html"),
    ):
        output.mkdir(parents=True, exist_ok=True)
        (output / name).write_text(label)


@pytest.mark.parametrize("failure", [None, "frontend", "desktop", "missing"])
def test_development_desktop_rebuild_keeps_old_build_on_failure(
    monkeypatch, tmp_path: Path, failure: str | None
) -> None:
    _write_build(tmp_path, "old")
    built: list[Path] = []

    def build(command: list[str], **kwargs: object) -> None:
        assert command == ["npm", "run", "build"]
        cwd = kwargs["cwd"]
        built.append(cwd)
        if cwd == tmp_path / "frontend":
            (tmp_path / "frontend/dist").mkdir()
            (tmp_path / "frontend/dist/index.html").write_text("new")
            if failure == "frontend":
                raise subprocess.CalledProcessError(1, command)
            return
        (tmp_path / "apps/desktop/dist").mkdir()
        if failure == "desktop":
            raise subprocess.CalledProcessError(1, command)
        if failure != "missing":
            (tmp_path / "apps/desktop/dist/main.js").write_text("new")

    monkeypatch.setattr(cli, "run_command", build)
    if failure:
        with pytest.raises((OSError, subprocess.CalledProcessError)):
            cli._rebuild_development_ui(tmp_path)
        expected = "old"
    else:
        cli._rebuild_development_ui(tmp_path)
        assert built == [tmp_path / "frontend", tmp_path / "apps/desktop"]
        expected = "new"
    assert (tmp_path / "frontend/dist/index.html").read_text() == expected
    assert (tmp_path / "apps/desktop/dist/main.js").read_text() == expected
    assert not list((tmp_path / ".suzent").iterdir())


def test_stop_source_desktop_kills_only_this_checkouts_electron(
    monkeypatch, tmp_path: Path
) -> None:
    electron = tmp_path / "apps/desktop/node_modules/electron/dist/electron.exe"
    killed: list[int] = []

    class Process:
        def __init__(self, pid: int, exe: str | None) -> None:
            self.pid = pid
            self.info = {"exe": exe}

        def kill(self) -> None:
            killed.append(self.pid)

    processes = [
        Process(1, str(electron)),
        Process(2, str(tmp_path / "other/electron.exe")),
        Process(3, None),
    ]
    monkeypatch.setattr(cli.psutil, "process_iter", lambda attrs: processes)
    monkeypatch.setattr(cli.psutil, "wait_procs", lambda procs, timeout: None)

    cli._stop_source_desktop(tmp_path)

    assert killed == [1]
