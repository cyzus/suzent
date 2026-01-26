# Release Guide

This guide describes how to release a new version of Suzent. The process is automated using GitHub Actions, but requires a manual version bump and tagging.

## 1. Bump Version

We use a helper script to consistently update the version number across all necessary files (`package.json`, `Cargo.toml`, `pyproject.toml`, etc.).

### Usage

Run the `bump_version.py` script from the root directory:

```bash
# Bump patch version (e.g., 0.1.0 -> 0.1.1)
python scripts/bump_version.py patch

# Bump minor version (e.g., 0.1.0 -> 0.2.0)
python scripts/bump_version.py minor

# Bump major version (e.g., 0.1.0 -> 1.0.0)
python scripts/bump_version.py major

# Set specific version
python scripts/bump_version.py 1.2.3
```

The script will automatically updates:
- `src-tauri/tauri.conf.json`
- `src-tauri/package.json`
- `src-tauri/Cargo.toml`
- `frontend/package.json`
- `pyproject.toml`

At the end, it will output the git commands you need to run to commit the changes.

## 2. Trigger Release (commit & tag)

After bumping the version, you need to commit the changes and create a git tag. The GitHub Action workflow listens for tags starting with `v` (e.g., `v0.1.1`).

```bash
# 1. Commit the version bump
git commit -am "chore: bump version to 0.1.1"

# 2. Create a tag
git tag v0.1.1

# 3. Push to GitHub
git push && git push --tags
```

## 3. Automated Build

Once the tag is pushed, the **[Build Desktop Apps](../../.github/workflows/build-desktop.yml)** workflow will automatically trigger. It performs the following steps:

1.  **Builds Backend**: Compiles the Python backend using Nuitka.
2.  **Builds Frontend**: Builds the React frontend.
3.  **Builds Desktop App**: Bundles everything into a Tauri application.
    - **Windows**: `.msi`
    - **macOS**: `.dmg` (Intel & Apple Silicon)
    - **Linux**: `.AppImage` / `.deb` (Ubuntu)
4.  **Publishes Release**: Creates a Draft Release on GitHub with all artifacts attached.

## 4. Finalize Release

1.  Go to the [GitHub Releases](https://github.com/cyzus/suzent/releases) page.
2.  Find the new Draft Release.
3.  Edit the release notes to include the changelog.
4.  Click **Publish release**.
