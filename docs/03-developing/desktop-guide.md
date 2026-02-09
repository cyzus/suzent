# SUZENT Desktop Application

SUZENT uses Tauri 2.0 to create native desktop applications for Windows, macOS, and Linux. The Python backend is bundled as a standalone Python distribution with `uv` for dependency management, and the React frontend is served through Tauri's native webview.

## Documentation

| Document | Purpose |
|----------|---------|
| [development-guide.md](./development-guide.md) | Complete development guide (includes Quick Start) |

## Architecture

```
+-------------------------------------------+
|           Tauri Application               |
|  +--------------+    +------------------+ |
|  |   Webview    |    |  Rust Process    | |
|  |   (React)    |    |                  | |
|  |              |    |  - Backend       | |
|  |  Frontend    |--->|    Lifecycle     | |
|  |  Built       |    |  - Port Mgmt     | |
|  |  Assets      |    |  - First-Run     | |
|  +--------------+    |    Setup         | |
|         |            +------------------+ |
|         +-----HTTP API------+             |
|             (localhost:dynamic)           |
+-------------------------------------------+
                    |
            +-------v--------+
            | Python Backend |
            | (uv-managed    |
            |  venv)         |
            |                |
            | - Starlette    |
            | - LanceDB      |
            | - SQLite       |
            +----------------+
```

### Bundled Resources

When built for production, the installer includes:

```
resources/
├── python/          # Standalone Python 3.12 (~15MB compressed)
│   ├── python.exe
│   ├── python312.dll
│   └── Lib/...
├── wheel/           # Pre-built suzent wheel
│   └── suzent-x.x.x-py3-none-any.whl
├── config/          # Example config files
├── skills/          # Bundled skills
└── uv.exe           # uv package manager binary
```

On first launch, the Rust side:
1. Creates a virtual environment using `uv` and the bundled Python
2. Installs the suzent wheel into the venv
3. Installs Playwright Chromium browser
4. Copies config and skills to the app data directory

## Prerequisites

### Build Tools

**All platforms:**
- Node.js 20.x or higher
- Python 3.12 or higher
- Rust 1.75 or higher (https://rustup.rs/)
- Python `build` package:
  ```bash
  uv pip install build
  ```

**Windows:**
- Microsoft Visual C++ Build Tools
- WebView2 Runtime (usually pre-installed on Windows 10/11)

**macOS:**
```bash
xcode-select --install
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev \
  libappindicator3-dev librsvg2-dev patchelf
```

## Quick Start (Development)

**Desktop app mode** (requires Rust):
```bash
# Terminal 1: Start backend
python src/suzent/server.py

# Terminal 2: Start Tauri
cd src-tauri
npm install
npm run dev
```

**Browser mode** (no Rust needed):
```bash
# Terminal 1: Start backend
python src/suzent/server.py

# Terminal 2: Start frontend
cd frontend && npm run dev
# Then open http://localhost:5173
```

See [development-guide.md](./development-guide.md) for detailed development instructions.

## Production Build

Build the complete standalone application:

```bash
cd src-tauri
npm run build:full
```

This command automatically:
1. Bundles the Python runtime, uv, and suzent wheel (`npm run bundle:python`)
2. Builds the Tauri application with bundled resources (`npm run build`)

> **Note:** The frontend is built as part of the Tauri build step.

Or use convenience scripts:

**Windows (PowerShell):**
```powershell
.\scripts\build_tauri.ps1
```

**macOS/Linux:**
```bash
chmod +x scripts/build_tauri.sh
./scripts/build_tauri.sh
```

The convenience scripts run 3 steps:
1. Build the React frontend
2. Bundle Python backend (`python scripts/bundle_python.py`)
3. Build the Tauri application

### Build Artifacts

Find installers at:

| Platform | Location |
|----------|----------|
| Windows | `src-tauri/target/release/bundle/msi/SUZENT_x.x.x_x64_en-US.msi` |
| macOS | `src-tauri/target/release/bundle/dmg/SUZENT_x.x.x_x64.dmg` |
| Linux | `src-tauri/target/release/bundle/appimage/suzent_x.x.x_amd64.AppImage` |

### Manual Build Steps

If you prefer to build step by step:

1. **Install Dependencies**
   ```bash
   cd src-tauri && npm install
   cd ../frontend && npm install
   cd ..
   ```

2. **Build Frontend**
   ```bash
   cd frontend
   npm run build
   cd ..
   ```

3. **Bundle Python Backend**
   ```bash
   python scripts/bundle_python.py
   ```
   Downloads a standalone Python distribution, the `uv` binary, and builds a suzent wheel into `src-tauri/resources/`. Also copies example configs and skills.

4. **Build Tauri Application**
   ```bash
   cd src-tauri
   npm run build
   ```

## First-Run Behavior

When the desktop app launches for the first time (or after an update):

1. **Venv Creation** (~10-30 seconds): The Rust side runs `uv venv` with the bundled Python, then `uv pip install` with the bundled wheel. A version marker file prevents re-running on subsequent launches.
2. **Playwright Install** (~1-2 minutes): Chromium browser is downloaded for the browsing tool. This is non-fatal — if it fails, Playwright will retry on first use.
3. **Config Sync**: Example configs and skills are copied to the app data directory (only missing files are added, existing files are preserved).

## Application Data Location

When running as a bundled application, SUZENT stores all user data in the standard OS application data directory:

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\com.suzent.app\` (e.g., `C:\Users\Username\AppData\Roaming\com.suzent.app\`) |
| macOS | `~/Library/Application Support/com.suzent.app/` |
| Linux | `~/.config/com.suzent.app/` (or `$XDG_CONFIG_HOME`) |

This directory contains:
- `backend-venv/`: Python virtual environment with suzent installed
- `chats.db`: SQLite database for chat history
- `memory/`: LanceDB vector database for long-term memory
- `skills/`: Custom user skills
- `sandbox-data/`: Data generated in the code execution sandbox
- `config/`: Configuration files

## Project Structure

```
suzent/
├── frontend/              # React frontend (Vite)
│   ├── src/
│   ├── package.json
│   └── dist/              # Built output
├── src/suzent/            # Python backend
│   ├── server.py          # Entry point
│   └── ...
├── src-tauri/             # Tauri desktop wrapper
│   ├── src/               # Rust code
│   │   ├── main.rs        # App entry
│   │   └── backend.rs     # Backend manager (venv setup + process launch)
│   ├── resources/         # Bundled resources (after bundle_python.py)
│   ├── package.json       # Tauri CLI
│   ├── Cargo.toml         # Rust deps
│   ├── tauri.conf.json    # Dev config
│   └── tauri.conf.prod.json  # Prod config
├── scripts/               # Build scripts
│   ├── bundle_python.py   # Bundle Python + uv + wheel
│   ├── build_tauri.sh     # Unix build script
│   └── build_tauri.ps1    # Windows build script
└── config/                # Configuration
```

## Troubleshooting

### Bundle Script Fails

**Missing `build` package:**
```bash
uv pip install build
```

**Network issues downloading Python/uv:**
Re-run `python scripts/bundle_python.py`. The script cleans and re-downloads everything.

### Cargo Build Fails

**Outdated Rust:**
```bash
rustup update
```

**Corrupted build cache:**
```bash
cd src-tauri
cargo clean
```

### Backend Fails to Start in Built App

- Check `~/suzent_startup.log` for backend startup logs
- Verify `backend-venv/` exists in the app data directory
- Delete `backend-venv/` to force venv re-creation on next launch

### Frontend Cannot Connect to Backend

- Verify `window.__SUZENT_BACKEND_PORT__` is set in the browser console
- Check that all API calls use `getApiBase()` prefix
- Ensure CSP settings in `tauri.conf.json` allow localhost connections

### Large Bundle Size

The bundled application may be 80-150MB due to:
- Python runtime and dependencies
- uv binary
- LanceDB native libraries

Playwright/Chromium browsers (~300MB) are downloaded separately on first launch and stored in the user's data directory.

## Resources

- [Tauri Documentation](https://v2.tauri.app/)
- [uv Documentation](https://docs.astral.sh/uv/)
- [python-build-standalone](https://github.com/indygreg/python-build-standalone)
