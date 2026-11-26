import importlib
import subprocess
from pathlib import Path

import pytest

cli = importlib.import_module("suzent.cli.main")


def _shell_built(root: Path) -> None:
    electron = root / "apps/desktop/node_modules/electron"
    (electron / "dist").mkdir(parents=True, exist_ok=True)
    (electron / "path.txt").write_text("electron")
    (electron / "dist/electron").write_bytes(b"exe")
    (root / "apps/desktop/dist").mkdir(parents=True, exist_ok=True)
    (root / "apps/desktop/dist/main.js").write_text("")
    (root / "frontend/dist").mkdir(parents=True, exist_ok=True)
    (root / "frontend/dist/index.html").write_text("")


@pytest.mark.parametrize("failure", [None, "build", "missing"])
def test_development_desktop_builds_web_ui_then_shell(
    monkeypatch, tmp_path: Path, failure: str | None
) -> None:
    built: list[Path] = []

    def build(command: list[str], **kwargs: object) -> None:
        assert command == ["npm", "run", "build"]
        built.append(kwargs["cwd"])
        if failure == "build":
            raise subprocess.CalledProcessError(1, command)
        if failure != "missing" and kwargs["cwd"] == tmp_path / "apps/desktop":
            _shell_built(tmp_path)

    monkeypatch.setattr(cli, "run_command", build)
    if failure:
        with pytest.raises((OSError, subprocess.CalledProcessError)):
            cli._rebuild_development_ui(tmp_path)
    else:
        cli._rebuild_development_ui(tmp_path)
        assert built == [tmp_path / "frontend", tmp_path / "apps/desktop"]
