# Release Guide

This guide describes how to release a new version of Suzent. The process is automated using GitHub Actions, but requires a manual version bump and tagging.

## 1. Update Changelog

Generate a draft from commits since the last tag, then edit it into `CHANGELOG.md` before bumping the version — so the changelog and version bump land in the same commit.

```bash
python scripts/bump_version.py --changelog
```

This prints all `feat:`, `fix:`, `refactor:`, and `perf:` commits since the last tag. Copy the output into `CHANGELOG.md`, edit for clarity, then save.

> [!TIP]
> The draft only picks up commits with conventional prefixes. Commits without a prefix are skipped, so keeping commit messages consistent ensures nothing is missed.

## 2. Bump Version

With the changelog already updated, run the version bump. This updates version numbers across all necessary files (`package.json`, `Cargo.toml`, `pyproject.toml`, etc.) and prints the changelog draft again for reference.

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

Files updated:
- `src-tauri/tauri.conf.json`
- `src-tauri/tauri.conf.prod.json`
- `src-tauri/package.json`
- `src-tauri/Cargo.toml`
- `src-tauri/Cargo.lock`
- `frontend/package.json`
- `pyproject.toml`
- npm lock files
- `uv.lock`

> [!IMPORTANT]
> The version in the changelog header (e.g., `[v0.2.3]`) must match the git tag exactly. Release notes are automatically extracted from this section.

## 3. Run Pre-commit Hooks

Before committing the version bump and changelog, ensure all code is properly formatted and linted. The CI workflow runs `ruff check .` and will fail if there are linting issues.

```bash
# Run pre-commit hooks on all files
pre-commit run --all-files

# Or manually run ruff
ruff check . --fix
ruff format .
```

> [!TIP]
> Install pre-commit hooks to run automatically before each commit:
> ```bash
> pre-commit install
> ```

## 4. Commit and Tag

Commit the changelog and version bump together, then create a git tag. The GitHub Action workflow listens for tags starting with `v`.

```bash
# 1. Commit the version bump, lock files, and changelog
git add .
git commit -m "chore: bump version to 0.1.1"

# 2. Create a tag
git tag v0.1.1

# 3. Push to GitHub
git push && git push --tags
```

## 6. Automated Build & Release

Once the tag is pushed, the **[Build Desktop Apps](../../.github/workflows/build-desktop.yml)** workflow will automatically trigger. It performs the following steps:

1.  **Extracts Release Notes**: Reads the changelog entry for the tagged version from `CHANGELOG.md`.
2.  **Bundles Python Backend**: Downloads standalone Python + uv, builds suzent wheel into `src-tauri/resources/`.
3.  **Builds Frontend**: Builds the React frontend.
4.  **Builds Desktop App**: Bundles everything into a Tauri application.
    - **Windows**: `.msi`
    - **macOS**: `.dmg` (Intel & Apple Silicon)
    - **Linux**: `.AppImage` / `.deb` (Ubuntu)
5.  **Publishes Release**: Creates a GitHub Release with:
    - Release notes from the changelog (fully automated!)
    - All platform artifacts attached

## 7. Verify Release

1.  Go to the [GitHub Releases](https://github.com/cyzus/suzent/releases) page.
2.  Verify the release was created with the correct version and release notes.
3.  Download and test the artifacts if needed.

## Troubleshooting

### Pipeline Fails

If you forgot to run pre-commit hooks or want to revert the release:

1. **Delete the problematic tag**:
   ```bash
   # Delete locally
   git tag -d v0.2.2  # Replace with your tag version
   # Delete remotely
   git push origin :refs/tags/v0.2.2
   ```

   
2. **Recreate the tag**:
   ```
   # Create the tag on the latest commit (with precommit fixes)      
   git tag v0.2.2

   # Push everything
   git push && git push --tags   
   ```

### Missing Changelog Entry

If the workflow fails because the changelog entry is missing or doesn't match the tag version:

1. Ensure there's an entry in `CHANGELOG.md` with the exact version matching your tag.
2. The header must use the format: `## [v0.2.2] - 2026-02-02` (version must match the git tag).
3. Follow steps 3-4 above to delete and recreate the tag after updating the changelog.
