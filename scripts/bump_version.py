#!/usr/bin/env python3
"""
Unified version bumper for Suzent.
Updates version in:
- src-tauri/tauri.conf.json
- src-tauri/package.json
- src-tauri/Cargo.toml
- frontend/package.json
- pyproject.toml
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Files to update
FILES = {
    "tauri_conf": Path("src-tauri/tauri.conf.json"),
    "tauri_pkg": Path("src-tauri/package.json"),
    "cargo": Path("src-tauri/Cargo.toml"),
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
        f.write("\n") # Add trailing newline
    
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

def main():
    parser = argparse.ArgumentParser(description="Bump project version")
    parser.add_argument("version", help="New version (x.y.z) or bump type (major/minor/patch)")
    parser.add_argument("--check", action="store_true", help="Check for consistency only")
    
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
                with open(path, "r") as f: v = json.load(f)["version"]
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
    update_json(PATHS["tauri_pkg"], new_version)
    update_json(PATHS["frontend_pkg"], new_version)
    update_toml(PATHS["cargo"], new_version)
    update_toml(PATHS["pyproject"], new_version)
    
    print("\nDone! Don't forget to commit:")
    print(f'git commit -am "chore: bump version to {new_version}"')
    print(f'git tag v{new_version}')

if __name__ == "__main__":
    main()
