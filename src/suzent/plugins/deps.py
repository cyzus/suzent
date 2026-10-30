"""Installing the packages plugins depend on.

Built-in plugins name extras of Suzent's own ``pyproject.toml``; those are
synced into the main environment with uv. Third-party plugins list pip
requirements, which go into a per-plugin directory outside the environment, so
the exact ``uv sync`` run on upgrade cannot remove them.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from suzent.logger import get_logger

logger = get_logger(__name__)

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXTRA_MARKER_RE = re.compile(r"""extra\s*==\s*["']([^"']+)["']""")


class DependencyError(RuntimeError):
    """Installing a plugin's packages failed or is impossible here."""


def find_uv() -> str | None:
    """uv on PATH, or where its installers put it (as the desktop app looks)."""
    found = shutil.which("uv")
    if found:
        return found
    name = "uv.exe" if os.name == "nt" else "uv"
    for candidate in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        if (candidate / name).is_file():
            return str(candidate / name)
    return None


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def extra_requirements(extra: str, distribution: str = "suzent") -> list[str]:
    """Package names that ``distribution[extra]`` adds."""
    try:
        requires = importlib.metadata.requires(distribution) or []
    except importlib.metadata.PackageNotFoundError:
        return []
    names = []
    for requirement in requires:
        requirement_text, _, marker = requirement.partition(";")
        if extra not in _EXTRA_MARKER_RE.findall(marker):
            continue
        match = _NAME_RE.match(requirement_text)
        if match:
            names.append(match.group(1))
    return names


def _installed(name: str, path: list[str] | None = None) -> bool:
    wanted = _normalize(name)
    distributions = importlib.metadata.distributions(**({"path": path} if path else {}))
    return any(
        _normalize(dist.metadata["Name"] or "") == wanted for dist in distributions
    )


def missing_packages(
    extras: list[str], dependencies: list[str], deps_dir: Path | None
) -> list[str]:
    """Packages a plugin declares that are not installed where it would find them."""
    missing = [
        name
        for extra in extras
        for name in extra_requirements(extra)
        if not _installed(name)
    ]
    for requirement in dependencies:
        match = _NAME_RE.match(requirement)
        if not match:
            continue
        name = match.group(1)
        in_own_dir = (
            deps_dir is not None
            and deps_dir.is_dir()
            and _installed(name, [str(deps_dir)])
        )
        if not in_own_dir and not _installed(name):
            missing.append(name)
    return missing


def sync_command(
    uv: str, extras: list[str], *, development: bool = False, inexact: bool = False
) -> list[str]:
    """The ``uv sync`` for Suzent's environment with these extras."""
    command = [uv, "sync", "--frozen"]
    if inexact:
        # Adds what is missing without removing anything, so it is safe while
        # the backend is running from this environment.
        command.append("--inexact")
    for extra in dict.fromkeys([*extras, *(["dev"] if development else [])]):
        command.extend(["--extra", extra])
    return command


def _run(command: list[str], cwd: Path | None = None) -> None:
    logger.info(f"Installing plugin dependencies: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip().splitlines()
        raise DependencyError("\n".join(output[-15:]) or f"{command[0]} failed")


def sync_extras(project_dir: Path, extras: list[str]) -> None:
    """Install the packages of ``extras`` into the running environment."""
    if not extras:
        return
    if not (project_dir / "uv.lock").is_file():
        raise DependencyError(
            "This Suzent was not installed from source, so its packages cannot be "
            f"synced here. Install them with: pip install 'suzent[{','.join(extras)}]'"
        )
    uv = find_uv()
    if uv is None:
        raise DependencyError(
            "uv was not found; install it from https://docs.astral.sh/uv/"
        )
    _run(sync_command(uv, extras, inexact=True), cwd=project_dir)
    importlib.invalidate_caches()


def install_requirements(requirements: list[str], target: Path) -> None:
    """Install a third-party plugin's requirements into its own directory."""
    if not requirements:
        return
    uv = find_uv()
    target.mkdir(parents=True, exist_ok=True)
    if uv is not None:
        command = [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(target),
        ]
    else:
        command = [sys.executable, "-m", "pip", "install", "--target", str(target)]
    _run([*command, *requirements])
    importlib.invalidate_caches()
