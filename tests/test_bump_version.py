import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.bump_version import (
    VERSION_FILES,
    VersionFile,
    bump_semver,
    generate_changelog_draft,
    read_version,
    write_version,
)


@pytest.mark.parametrize(
    ("bump_type", "expected"),
    [
        ("patch", "1.2.4"),
        ("minor", "1.3.0"),
        ("major", "2.0.0"),
    ],
)
def test_bump_semver(bump_type: str, expected: str) -> None:
    assert bump_semver("1.2.3", bump_type) == expected


def test_version_files_cover_main_app_and_installer() -> None:
    paths = {target.path for target in VERSION_FILES}

    assert "pyproject.toml" in paths
    assert "src-tauri/Cargo.lock" in paths
    assert "apps/suzent-installer/package.json" in paths
    assert "apps/suzent-installer/Cargo.lock" in paths


def test_package_lock_updates_both_project_versions(tmp_path: Path) -> None:
    path = tmp_path / "package-lock.json"
    path.write_text(
        json.dumps(
            {
                "name": "example",
                "version": "0.1.0",
                "packages": {"": {"name": "example", "version": "0.1.0"}},
            }
        ),
        encoding="utf-8",
    )
    target = VersionFile("package-lock.json", "package-lock")

    write_version(path, target, "0.2.0")

    assert read_version(path, target) == "0.2.0"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["packages"][""]["version"] == "0.2.0"


def test_named_lock_updates_only_selected_package(tmp_path: Path) -> None:
    path = tmp_path / "Cargo.lock"
    path.write_text(
        '[[package]]\nname = "dependency"\nversion = "9.9.9"\n\n'
        '[[package]]\nname = "suzent-installer"\nversion = "0.6.6"\n',
        encoding="utf-8",
    )
    target = VersionFile("Cargo.lock", "named-lock", "suzent-installer")

    write_version(path, target, "0.7.1")

    content = path.read_text(encoding="utf-8")
    assert 'name = "dependency"\nversion = "9.9.9"' in content
    assert read_version(path, target) == "0.7.1"


def test_changelog_accepts_scopes_and_keeps_unprefixed_changes(
    tmp_path: Path,
) -> None:
    draft = generate_changelog_draft(
        "1.0.0",
        tmp_path,
        subjects=[
            "feat(ui): add update controls",
            "fix: avoid release race",
            "Improve desktop packaging",
            "docs: refresh release guide",
        ],
    )

    assert "- Add update controls" in draft
    assert "- Avoid release race" in draft
    assert "- Improve desktop packaging" in draft
    assert "refresh release guide" not in draft


def test_changelog_cli_uses_utf8_when_console_defaults_to_gbk() -> None:
    root = Path(__file__).resolve().parent.parent
    environment = {**os.environ, "PYTHONIOENCODING": "gbk"}

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/bump_version.py"),
            "patch",
            "--changelog",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "⚡".encode() in result.stdout
