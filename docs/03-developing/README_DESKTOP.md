# SUZENT Desktop Application

SUZENT has been wrapped with Tauri 2.0 to create native desktop applications for Windows, macOS, and Linux. The Python backend is bundled as a standalone executable using Nuitka, and the React frontend is served through Tauri's native webview.

## Documentation

| Document | Purpose |
|----------|---------|
| [DEV_GUIDE.md](./DEV_GUIDE.md) | Complete development guide (includes Quick Start) |
| [TAURI_BUILD.md](./TAURI_BUILD.md) | Production build and deployment |

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

| Requirement | Version | Notes |
|-------------|---------|-------|
| Node.js | 20+ | Required for frontend and Tauri CLI |
| Python | 3.12+ | Required for backend |
| Rust | 1.75+ | Required for desktop app (not needed for browser mode) |

Install Rust from https://rustup.rs/

## Quick Start

**Desktop app mode** (requires Rust):
```bash
# Terminal 1: Start backend
python src/suzent/server.py

# Terminal 2: Start Tauri
cd src-tauri && npm run dev
```

**Browser mode** (no Rust needed):
```bash
# Terminal 1: Start backend
python src/suzent/server.py

# Terminal 2: Start frontend
cd frontend && npm run dev
# Then open http://localhost:5173
```

See [START_DEV.md](./START_DEV.md) for detailed instructions.

## Production Build

```bash
cd src-tauri
npm run build:full
```

Build artifacts location:
- **Windows**: `src-tauri/target/release/bundle/msi/`
- **macOS**: `src-tauri/target/release/bundle/dmg/`
- **Linux**: `src-tauri/target/release/bundle/appimage/`

See [TAURI_BUILD.md](./TAURI_BUILD.md) for complete build instructions.

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

## Application Data Location

When running as a bundled application, SUZENT stores data in platform-specific locations:

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%/com.suzent.app/` |
| macOS | `~/Library/Application Support/com.suzent.app/` |
| Linux | `~/.local/share/com.suzent.app/` |

Data stored:
- `chats.db` - SQLite database for chat history
- `memory/` - LanceDB vector database
- `sandbox-data/` - Uploaded files and sandbox data
- `skills/` - Custom skills

## Known Limitations

- MicroSandbox is disabled in bundled builds (complex to bundle Docker/containerd)
- File operations use host system instead of containerized sandbox
- crawl4ai browser binaries add ~100MB to bundle size

## Resources

- [Tauri Documentation](https://v2.tauri.app/)
- [Nuitka Documentation](https://nuitka.net/doc/user-manual.html)
- [Embedding External Binaries in Tauri](https://v2.tauri.app/develop/sidecar/)
