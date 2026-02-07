# SUZENT Desktop Application

SUZENT has been wrapped with Tauri 2.0 to create native desktop applications for Windows, macOS, and Linux. The Python backend is bundled as a standalone executable using Nuitka, and the React frontend is served through Tauri's native webview.

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
|  |  Assets      |    |  - IPC Bridge    | |
|  +--------------+    +------------------+ |
|         |                   |             |
|         +-----HTTP API------+             |
|             (localhost:dynamic)           |
+-------------------------------------------+
                    |
            +-------v--------+
            | Python Backend |
            |  (Bundled exe) |
            |                |
            | - Starlette    |
            | - LanceDB      |
            | - SQLite       |
            +----------------+
```

## Prerequisites

### Build Tools

**All platforms:**
- Node.js 20.x or higher
- Python 3.12 or higher
- Rust 1.75 or higher (https://rustup.rs/)
- Nuitka for Python compilation:
  ```bash
  uv pip install nuitka orderedset zstandard
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
1. Builds the frontend (`npm run build:frontend`)
2. Builds the Python backend with Nuitka (`npm run build:backend`)
3. Builds the Tauri application and bundles everything (`npm run build`)

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

3. **Build Python Backend**
   ```bash
   python scripts/build_backend.py
   ```
   Creates a standalone executable at `src-tauri/binaries/suzent-backend-<target-triple>` (e.g., `suzent-backend-x86_64-pc-windows-msvc.exe`). Tauri requires this strict naming convention for sidecars.

4. **Build Tauri Application**
   ```bash
   cd src-tauri
   npm run build
   ```

## Application Data Location

When running as a bundled application, SUZENT stores all user data in the standard OS application data directory:

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\com.suzent.app\` (e.g., `C:\Users\Username\AppData\Roaming\com.suzent.app\`) |
| macOS | `~/Library/Application Support/com.suzent.app/` |
| Linux | `~/.config/com.suzent.app/` (or `$XDG_CONFIG_HOME`) |

This directory contains:
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
│   │   └── backend.rs     # Backend manager
│   ├── binaries/          # Compiled Python backend (after build)
│   ├── package.json       # Tauri CLI
│   ├── Cargo.toml         # Rust deps
│   ├── tauri.conf.json    # Dev config
│   └── tauri.conf.prod.json  # Prod config
├── scripts/               # Build scripts
│   ├── build_backend.py   # Nuitka build script
│   ├── build_tauri.sh     # Unix build script
│   └── build_tauri.ps1    # Windows build script
└── config/                # Configuration
```

## Troubleshooting

### Nuitka Build Fails

**Missing dependencies:**
```bash
uv pip install -r requirements.txt
```

**Outdated Nuitka:**
```bash
uv pip install --upgrade nuitka
```

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

- Check `src-tauri/binaries/` contains the backend executable
- Verify Python dependencies were bundled correctly
- Check application logs in the app data directory

### Frontend Cannot Connect to Backend

- Verify `window.__SUZENT_BACKEND_PORT__` is set in the browser console
- Check that all API calls use `API_BASE` prefix
- Ensure CSP settings in `tauri.conf.json` allow localhost connections

### Large Bundle Size

The bundled application may be 200-500MB due to:
- Python runtime and dependencies
- Playwright/Chromium binaries (for crawl4ai)
- LanceDB native libraries

Optimizations:
- Selective Playwright binary inclusion
- Strip debug symbols: `cargo tauri build --release`
- Compress final installers

## Resources

- [Tauri Documentation](https://v2.tauri.app/)
- [Nuitka Documentation](https://nuitka.net/doc/user-manual.html)
- [Embedding External Binaries in Tauri](https://v2.tauri.app/develop/sidecar/)
