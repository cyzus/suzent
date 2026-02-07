# Utility Scripts

This directory contains automation scripts for the Suzent project.

## Development

### `suzent start`
 
 The main entry point for development. It simultaneously starts:
 - FastAP/Uvicorn backend (Port determined dynamically, usually 8000+)
 - Tauri/Vite frontend (Port 1420)
 
 Usage: `suzent start`

## Build

### `build_backend.py`
Compiles the Python backend into a standalone executable using Nuitka.

```bash
python scripts/build_backend.py
```

### `build_tauri`
Builds the complete desktop application (frontend + backend bundle).

- **Windows**: `scripts\build_tauri.ps1`
- **Linux/macOS**: `scripts/build_tauri.sh`

## Maintenance

### `bump_version.py`
Updates version numbers across `pyproject.toml`, `package.json`, and Cargo files.

```bash
python scripts/bump_version.py [major|minor|patch]
```

### `fix_timestamps.py`
Utility to fix file timestamps (if needed for build reproducibility).
