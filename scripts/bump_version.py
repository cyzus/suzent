#!/usr/bin/env python3
"""Synchronize every Suzent package version and prepare its changelog entry."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class VersionFile:
    path: str
    kind: str
    package: str | None = None


VERSION_FILES = (
    VersionFile("src-tauri/tauri.conf.json", "json"),
    VersionFile("src-tauri/tauri.conf.prod.json", "json"),
    VersionFile("src-tauri/package.json", "json"),
    VersionFile("frontend/package.json", "json"),
    VersionFile("apps/suzent-installer/tauri.conf.json", "json"),
    VersionFile("apps/suzent-installer/package.json", "json"),
    VersionFile("src-tauri/Cargo.toml", "toml"),
    VersionFile("apps/suzent-installer/Cargo.toml", "toml"),
    VersionFile("pyproject.toml", "toml"),
    VersionFile("frontend/package-lock.json", "package-lock"),
    VersionFile("src-tauri/package-lock.json", "package-lock"),
    VersionFile("apps/suzent-installer/package-lock.json", "package-lock"),
    VersionFile("src-tauri/Cargo.lock", "named-lock", "suzent"),
    VersionFile(
        "apps/suzent-installer/Cargo.lock",
        "named-lock",
        "suzent-installer",
    ),
    VersionFile("uv.lock", "named-lock", "suzent"),
)

TOML_VERSION_PATTERN = re.compile(r'(?m)^(version\s*=\s*")(\d+\.\d+\.\d+)(")')


def get_current_version(root: Path) -> str:
    path = root / "src-tauri/tauri.conf.json"
    return json.loads(path.read_text(encoding="utf-8"))["version"]


def bump_semver(current_version: str, bump_type: str) -> str:
    major, minor, patch = map(int, current_version.split("."))
    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    if bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown bump type: {bump_type}")


def _named_lock_pattern(package: str) -> re.Pattern[str]:
    return re.compile(
        rf'(\[\[package\]\]\r?\nname = "{re.escape(package)}"\r?\n'
        rf'version = ")(\d+\.\d+\.\d+)(")'
    )


def read_version(path: Path, target: VersionFile) -> str:
    if target.kind == "json":
        return json.loads(path.read_text(encoding="utf-8"))["version"]

    if target.kind == "package-lock":
        data = json.loads(path.read_text(encoding="utf-8"))
        top_level = data["version"]
        root_package = data["packages"][""]["version"]
        if top_level != root_package:
            return f"{top_level} (root package: {root_package})"
        return top_level

    content = path.read_text(encoding="utf-8")
    if target.kind == "toml":
        match = TOML_VERSION_PATTERN.search(content)
    elif target.kind == "named-lock" and target.package:
        match = _named_lock_pattern(target.package).search(content)
    else:
        raise ValueError(f"Unsupported version file type: {target.kind}")

    if not match:
        raise ValueError(f"Could not find project version in {path}")
    return match.group(2)


def write_version(path: Path, target: VersionFile, version: str) -> None:
    old_version = read_version(path, target)
    if old_version == version:
        print(f"  [SKIP] {target.path}")
        return

    if target.kind == "json":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    elif target.kind == "package-lock":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        data["packages"][""]["version"] = version
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    else:
        content = path.read_text(encoding="utf-8")
        pattern = (
            TOML_VERSION_PATTERN
            if target.kind == "toml"
            else _named_lock_pattern(target.package or "")
        )
        updated, count = pattern.subn(rf"\g<1>{version}\g<3>", content, count=1)
        if count != 1:
            raise ValueError(f"Could not update project version in {path}")
        path.write_text(updated, encoding="utf-8")

    print(f"  [UPDATE] {target.path}: {old_version} -> {version}")


def check_versions(root: Path, expected_version: str) -> bool:
    consistent = True
    for target in VERSION_FILES:
        path = root / target.path
        try:
            version = read_version(path, target)
        except (KeyError, OSError, ValueError) as error:
            print(f"  [ERROR] {target.path}: {error}")
            consistent = False
            continue

        if version != expected_version:
            print(f"  [MISMATCH] {target.path}: {version}")
            consistent = False
        else:
            print(f"  [OK] {target.path}")
    return consistent


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _previous_changelog_tag(root: Path, next_version: str) -> str | None:
    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.exists():
        return None

    next_tag = f"v{next_version}"
    tags = re.findall(
        r"(?m)^## \[(v\d+\.\d+\.\d+)\](?:\s|$)",
        changelog_path.read_text(encoding="utf-8"),
    )
    return next((tag for tag in tags if tag != next_tag), None)


def _release_boundary(root: Path, next_version: str) -> str | None:
    previous_tag = _previous_changelog_tag(root, next_version)
    if previous_tag:
        ancestor = _run_git(
            root,
            "merge-base",
            "--is-ancestor",
            previous_tag,
            "HEAD",
        )
        if ancestor.returncode == 0:
            return previous_tag

        release_subject = f"chore: release {previous_tag}".lower()
        history = _run_git(root, "log", "HEAD", "--format=%H%x09%s", "--no-merges")
        if history.returncode == 0:
            for line in history.stdout.splitlines():
                commit, separator, subject = line.partition("\t")
                if separator and subject.strip().lower() == release_subject:
                    return commit

    tag_result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    reachable_tag = tag_result.stdout.strip()
    return reachable_tag or None


def _git_subjects_since_last_release(
    root: Path,
    next_version: str,
) -> list[str]:
    boundary = _release_boundary(root, next_version)
    range_spec = f"{boundary}..HEAD" if boundary else "HEAD"
    result = subprocess.run(
        ["git", "log", range_spec, "--format=%s", "--no-merges"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def generate_changelog_draft(
    version: str,
    root: Path,
    subjects: list[str] | None = None,
) -> str:
    groups: dict[str, list[str]] = {"Added": [], "Changed": [], "Fixed": []}
    conventional = re.compile(
        r"^(feat|fix|refactor|perf)(?:\([^)]+\))?!?:\s*(.+)$",
        re.IGNORECASE,
    )
    ignored = re.compile(
        r"^(chore|ci|docs|test|style|build)(?:\([^)]+\))?!?:",
        re.IGNORECASE,
    )

    for subject in (
        subjects
        if subjects is not None
        else _git_subjects_since_last_release(root, version)
    ):
        match = conventional.match(subject)
        if match:
            commit_type, summary = match.groups()
            group = {
                "feat": "Added",
                "fix": "Fixed",
                "refactor": "Changed",
                "perf": "Changed",
            }[commit_type.lower()]
        elif ignored.match(subject) or subject.lower().startswith("release v"):
            continue
        else:
            group, summary = "Changed", subject

        summary = summary.strip()
        if summary:
            groups[group].append(summary[0].upper() + summary[1:])

    headers = {
        "Added": "### 🚀 Added",
        "Changed": "### ⚡ Changed",
        "Fixed": "### 🐛 Fixed",
    }
    lines = [f"## [v{version}] - {dt.date.today().isoformat()}", ""]
    for group, items in groups.items():
        if not items:
            continue
        lines.append(headers[group])
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    if all(not items for items in groups.values()):
        lines.extend(["### ⚡ Changed", "- Release maintenance", ""])
    return "\n".join(lines).rstrip() + "\n"


def _replace_changelog_entry(
    existing: str,
    version: str,
    draft: str,
) -> str | None:
    entry = re.compile(rf"(?ms)^## \[v{re.escape(version)}\][^\n]*\n.*?(?=^## \[v|\Z)")
    match = entry.search(existing)
    if not match:
        return None
    return existing[: match.start()] + draft.rstrip() + "\n\n" + existing[match.end() :]


def update_changelog(
    root: Path,
    version: str,
    *,
    replace_existing: bool = False,
) -> bool:
    changelog_path = root / "CHANGELOG.md"
    existing = changelog_path.read_text(encoding="utf-8")
    draft = generate_changelog_draft(version, root)
    replacement = _replace_changelog_entry(existing, version, draft)
    if replacement is not None and not replace_existing:
        print(f"  [SKIP] CHANGELOG.md already contains v{version}")
        return False
    if replacement is not None:
        if replacement == existing:
            print(f"  [SKIP] CHANGELOG.md v{version} is already current")
            return False
        changelog_path.write_text(replacement, encoding="utf-8")
        print(f"  [UPDATE] CHANGELOG.md: refreshed v{version}")
        return True

    first_release = re.search(r"(?m)^## \[v", existing)
    if first_release:
        position = first_release.start()
        updated = existing[:position] + draft + "\n" + existing[position:]
    else:
        updated = existing.rstrip() + "\n\n" + draft
    changelog_path.write_text(updated, encoding="utf-8")
    print(f"  [UPDATE] CHANGELOG.md: added v{version}")
    return True


def parse_version_argument(current_version: str, value: str) -> str:
    if value in {"major", "minor", "patch"}:
        return bump_semver(current_version, value)
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid version format: {value}")
    return value


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "version",
        nargs="?",
        help="New version (x.y.z) or bump type (major/minor/patch)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that all package versions match the canonical version",
    )
    parser.add_argument(
        "--changelog",
        action="store_true",
        help="Preview the next release changelog without changing files",
    )
    parser.add_argument(
        "--no-changelog",
        action="store_true",
        help="Synchronize versions without adding a changelog entry",
    )
    parser.add_argument(
        "--refresh-changelog",
        action="store_true",
        help="Replace the current version entry using the latest branch history",
    )
    parser.add_argument(
        "--print-version",
        action="store_true",
        help="Print only the canonical version",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    current_version = get_current_version(root)

    if args.print_version:
        print(current_version)
        return 0
    if args.check:
        print(f"Expected version: {current_version}")
        return 0 if check_versions(root, current_version) else 1
    if args.changelog:
        preview_version = (
            parse_version_argument(current_version, args.version)
            if args.version
            else current_version
        )
        print(generate_changelog_draft(preview_version, root), end="")
        return 0
    if args.refresh_changelog:
        update_changelog(root, current_version, replace_existing=True)
        return 0
    if not args.version:
        parser.error(
            "version is required unless --check, --changelog, or "
            "--refresh-changelog is used"
        )

    try:
        new_version = parse_version_argument(current_version, args.version)
        print(f"Synchronizing version: {current_version} -> {new_version}")
        for target in VERSION_FILES:
            write_version(root / target.path, target, new_version)
        if not args.no_changelog and new_version != current_version:
            update_changelog(root, new_version)
        if not check_versions(root, new_version):
            return 1
    except (KeyError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print("\nVersion files are synchronized. Review CHANGELOG.md before release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
