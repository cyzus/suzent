"""Version and build identity for the running Suzent source tree.

Deliberately free of heavy imports. This is read on every `suzent --version`,
and it previously lived in :mod:`suzent.routes.system_routes`, which pulls in
the database and the filesystem tools -- roughly 200ms to answer a question
that only needs `tomllib` and a few file reads.
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

UNKNOWN = "unknown"

# A short commit is what people paste into a bug report; eight characters stay
# unambiguous well past the point where git's default seven starts colliding.
SHORT_COMMIT_LENGTH = 8


def read_project_version(pyproject: Path) -> str | None:
    """Return the version a pyproject.toml declares for the suzent project."""
    try:
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get(
            "project", {}
        )
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if project.get("name") == "suzent" and isinstance(project.get("version"), str):
        return project["version"]
    return None


def _get_source_version(start: Path | None = None) -> str | None:
    """Find the nearest Suzent pyproject version for a source checkout."""

    source_file = (start or Path(__file__)).resolve()
    for parent in source_file.parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.is_file():
            continue
        if declared := read_project_version(pyproject):
            return declared
    return None


def get_backend_version() -> str:
    """Return the running backend package version."""

    source_version = _get_source_version()
    if source_version:
        return source_version
    try:
        return package_version("suzent")
    except PackageNotFoundError:
        return UNKNOWN


def _git_directory(marker: Path) -> Path | None:
    if marker.is_dir():
        return marker
    try:
        prefix, value = marker.read_text(encoding="utf-8").strip().split(":", 1)
    except (OSError, ValueError):
        return None
    if prefix.lower() != "gitdir":
        return None
    path = Path(value.strip())
    return path if path.is_absolute() else (marker.parent / path).resolve()


def _common_git_directory(git_dir: Path) -> Path:
    try:
        value = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        return git_dir
    path = Path(value)
    return path if path.is_absolute() else (git_dir / path).resolve()


def _valid_commit(value: str) -> str | None:
    commit = value.strip().lower()
    if len(commit) in (40, 64) and all(char in "0123456789abcdef" for char in commit):
        return commit
    return None


def _read_git_ref(git_dir: Path, ref: str) -> str | None:
    common_dir = _common_git_directory(git_dir)
    for root in (git_dir, common_dir):
        try:
            commit = _valid_commit((root / ref).read_text(encoding="utf-8"))
        except OSError:
            continue
        if commit:
            return commit

    try:
        packed_refs = (common_dir / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in packed_refs.splitlines():
        if not line or line.startswith(("#", "^")):
            continue
        try:
            commit, packed_ref = line.split(" ", 1)
        except ValueError:
            continue
        if packed_ref.strip() == ref:
            return _valid_commit(commit)
    return None


@lru_cache(maxsize=8)
def _read_source_commit(source_file: Path) -> str:
    for parent in source_file.resolve().parents:
        marker = parent / ".git"
        if not marker.exists():
            continue
        git_dir = _git_directory(marker)
        if git_dir is None:
            return UNKNOWN
        try:
            head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            return UNKNOWN
        if direct_commit := _valid_commit(head):
            return direct_commit
        if not head.startswith("ref:"):
            return UNKNOWN
        return _read_git_ref(git_dir, head.removeprefix("ref:").strip()) or UNKNOWN
    return UNKNOWN


def get_backend_commit(start: Path | None = None) -> str:
    """Return the backend commit without spawning a process in the request path."""

    configured = os.getenv("SUZENT_BUILD_COMMIT", "").strip()
    if configured:
        return configured
    return _read_source_commit(start or Path(__file__))


def short_commit(commit: str) -> str:
    """Abbreviate a commit for display, passing through the unknown marker."""
    return commit if commit == UNKNOWN else commit[:SHORT_COMMIT_LENGTH]
