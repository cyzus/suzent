#!/usr/bin/env python3
"""
Unified version bumper for Suzent.
Updates version in:
- src-tauri/tauri.conf.json
- src-tauri/tauri.conf.prod.json
- src-tauri/package.json
- src-tauri/Cargo.toml
- src-tauri/Cargo.lock
- frontend/package.json
- pyproject.toml
- frontend/package-lock.json
- src-tauri/package-lock.json
- uv.lock
"""

import argparse
import json
import re
import sys
from pathlib import Path
import subprocess

# Files to update
FILES = {
    "tauri_conf": Path("src-tauri/tauri.conf.json"),
    "tauri_conf_prod": Path("src-tauri/tauri.conf.prod.json"),
    "tauri_pkg": Path("src-tauri/package.json"),
    "cargo": Path("src-tauri/Cargo.toml"),
    "cargo_lock": Path("src-tauri/Cargo.lock"),
    "frontend_pkg": Path("frontend/package.json"),
    "pyproject": Path("pyproject.toml"),
}


def get_current_version(tauri_conf_path):
    with open(tauri_conf_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["version"]


def bump_semver(current_ver, bump_type):
    major, minor, patch = map(int, current_ver.split("."))
    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return current_ver


def update_json(path, new_version):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    old_version = data["version"]
    if old_version == new_version:
        print(f"  [SKIP] {path} already at {new_version}")
        return

    data["version"] = new_version

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")  # Add trailing newline

    print(f"  [UPDATE] {path}: {old_version} -> {new_version}")


def update_toml(path, new_version):
    """Simple regex based TOML updater to avoid destroying formatting/comments"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Matches version = "x.y.z"
    pattern = r'(version\s*=\s*")([\d\.]+)"'

    if not re.search(pattern, content):
        print(f"  [ERROR] Could not find version key in {path}")
        return

    new_content = re.sub(pattern, f'\\g<1>{new_version}"', content, count=1)

    if content == new_content:
        print(f"  [SKIP] {path} already at {new_version} (or pattern mismatch)")
        return

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  [UPDATE] {path} -> {new_version}")


def update_cargo_lock(path, new_version):
    """Update only the root suzent package entry in Cargo.lock."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r'(\[\[package\]\]\nname = "suzent"\nversion = ")([\d\.]+)(")'
    match = re.search(pattern, content)
    if not match:
        print(f"  [ERROR] Could not find suzent package entry in {path}")
        return

    old_version = match.group(2)
    if old_version == new_version:
        print(f"  [SKIP] {path} already at {new_version}")
        return

    new_content = re.sub(pattern, f"\\g<1>{new_version}\\g<3>", content, count=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  [UPDATE] {path}: {old_version} -> {new_version}")


def print_subprocess_error(label, error):
    print(f"  [ERROR] Failed to update {label}: {error}")
    stdout = (error.stdout or b"").decode("utf-8", errors="replace")
    stderr = (error.stderr or b"").decode("utf-8", errors="replace")
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip())


def main():
    parser = argparse.ArgumentParser(description="Bump project version")
    parser.add_argument(
        "version", help="New version (x.y.z) or bump type (major/minor/patch)"
    )
    parser.add_argument(
        "--check", action="store_true", help="Check for consistency only"
    )

    args = parser.parse_args()

    root = Path(__file__).parent.parent
    PATHS = {k: root / v for k, v in FILES.items()}

    current_version = get_current_version(PATHS["tauri_conf"])
    print(f"Current version: {current_version}")

    if args.check:
        # Check all files match
        mismatch = False
        for name, path in PATHS.items():
            if path.suffix == ".json":
                with open(path, "r") as f:
                    v = json.load(f)["version"]
            elif name == "cargo_lock":
                with open(path, "r", encoding="utf-8") as f:
                    match = re.search(
                        r'\[\[package\]\]\nname = "suzent"\nversion = "([\d\.]+)"',
                        f.read(),
                    )
                    v = match.group(1) if match else "unknown"
            else:
                with open(path, "r") as f:
                    match = re.search(r'version\s*=\s*"([\d\.]+)"', f.read())
                    v = match.group(1) if match else "unknown"

            if v != current_version:
                print(f"  [MISMATCH] {name}: {v}")
                mismatch = True
            else:
                print(f"  [OK] {name}")

        sys.exit(1 if mismatch else 0)

    # Determine new version
    if args.version in ["major", "minor", "patch"]:
        new_version = bump_semver(current_version, args.version)
    else:
        new_version = args.version
        if not re.match(r"^\d+\.\d+\.\d+$", new_version):
            print(f"Invalid version format: {new_version}")
            sys.exit(1)

    print(f"Bumping to: {new_version}")

    # Update files
    update_json(PATHS["tauri_conf"], new_version)
    update_json(PATHS["tauri_conf_prod"], new_version)
    update_json(PATHS["tauri_pkg"], new_version)
    update_json(PATHS["frontend_pkg"], new_version)
    update_toml(PATHS["cargo"], new_version)
    update_cargo_lock(PATHS["cargo_lock"], new_version)
    update_toml(PATHS["pyproject"], new_version)

    # Update lock files
    print("\nUpdating lock files...")
    try:
        subprocess.run(
            ["npm", "install"],
            cwd=root / "frontend",
            check=True,
            capture_output=True,
            shell=True,
        )
        print("  [OK] Updated frontend/package-lock.json")
    except subprocess.CalledProcessError as e:
        print_subprocess_error("frontend lock", e)

    try:
        subprocess.run(
            ["npm", "install"],
            cwd=root / "src-tauri",
            check=True,
            capture_output=True,
            shell=True,
        )
        print("  [OK] Updated src-tauri/package-lock.json")
    except subprocess.CalledProcessError as e:
        print_subprocess_error("src-tauri lock", e)

    try:
        print("Updating uv.lock...")
        subprocess.run(
            ["uv", "lock"],
            cwd=root,
            check=True,
            capture_output=True,
            shell=True,
        )
        print("  [OK] Updated uv.lock")
    except subprocess.CalledProcessError as e:
        print_subprocess_error("uv lock", e)

    print("\nDone! Lock files updated. Now commit and release:")
    print("git add .")
    print(f'git commit -m "chore: bump version to {new_version}"')
    print(f"git tag v{new_version}")
    print("git push && git push --tags")


if __name__ == "__main__":
    main()
