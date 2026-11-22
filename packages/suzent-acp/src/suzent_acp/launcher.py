"""Find the installed Suzent CLI and run ``suzent acp`` with the editor's pipes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


def _data_dir(env: Mapping[str, str], home: Path) -> Path:
    override = env.get("SUZENT_DATA_DIR", "").strip()
    return Path(override) if override else home / ".suzent"


def _saved_workspace(marker: Path) -> Path | None:
    try:
        text = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    # Older Windows installers saved the `\\?\C:\...` form of the path.
    if text.startswith("\\\\?\\") and text[5:6] == ":":
        text = text[4:]
    path = Path(text)
    return path if path.is_absolute() else None


def workspace_candidates(env: Mapping[str, str], home: Path) -> list[Path]:
    """Install workspaces in the order the desktop app itself resolves them."""
    candidates: list[Path] = []
    if override := env.get("SUZENT_DIR", "").strip():
        candidates.append(Path(override))
    if saved := _saved_workspace(_data_dir(env, home) / "install-dir.txt"):
        candidates.append(saved)
    candidates.append(home / "suzent")
    return candidates


def _venv_cli(workspace: Path, windows: bool) -> Path:
    if windows:
        return workspace / ".venv" / "Scripts" / "suzent.exe"
    return workspace / ".venv" / "bin" / "suzent"


def find_suzent(
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    windows: bool | None = None,
) -> str | None:
    """Return the Suzent CLI to run, or ``None`` when Suzent is not installed.

    Editors often start agents with a minimal PATH, so the install workspace's
    own virtualenv is checked before PATH.
    """
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    windows = os.name == "nt" if windows is None else windows
    for workspace in workspace_candidates(env, home):
        cli = _venv_cli(workspace, windows)
        if cli.is_file():
            return str(cli)
    return shutil.which("suzent", path=env.get("PATH"))


def run(argv: list[str]) -> int:
    """Run ``suzent acp`` with ``argv``, or answer the handshake without it."""
    cli = find_suzent()
    if cli is None:
        from suzent_acp.fallback import serve_not_installed

        return serve_not_installed(argv)
    command = [cli, "acp", *argv]
    if os.name != "nt":
        # Replacing the process keeps the editor's pipes and signals pointed at
        # the real agent, with nothing in between.
        os.execv(cli, command)
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 130


def main() -> None:
    sys.exit(run(sys.argv[1:]))
