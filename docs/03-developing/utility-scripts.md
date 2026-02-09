# Utility Scripts

This directory contains automation scripts for the Suzent project.

## Development

### `suzent start`

 The main entry point for development. It simultaneously starts:
 - Starlette/Uvicorn backend (Port determined dynamically, usually 8000+)
 - Tauri/Vite frontend (Port 1420)

 Usage: `suzent start`

## Build

### `bundle_python.py`
Bundles the Python backend for desktop distribution. Downloads and packages:
- Standalone Python 3.12 runtime (embeddable on Windows, python-build-standalone on macOS/Linux)
- `uv` package manager binary
- Pre-built suzent wheel (`.whl`)
- Example config files and skills directory

Output: `src-tauri/resources/` directory ready for Tauri bundling.

```bash
python scripts/bundle_python.py
```

> **Prerequisite**: `uv pip install build`

### `build_tauri`
Builds the complete desktop application (frontend + bundled Python backend + Tauri).

- **Windows**: `scripts\build_tauri.ps1`
- **Linux/macOS**: `scripts/build_tauri.sh`

Steps: Build frontend → Bundle Python → Build Tauri app.

## Maintenance

### `bump_version.py`
Updates version numbers across `pyproject.toml`, `package.json`, and Cargo files.

```bash
python scripts/bump_version.py [major|minor|patch]
```

### `fix_timestamps.py`
Utility to fix file timestamps (if needed for build reproducibility).
