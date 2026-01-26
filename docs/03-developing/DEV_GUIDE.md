# Development Guide

## Quick Start

Get SUZENT running in development mode in under 2 minutes.

| Mode | What opens | Rust required | Command |
|------|------------|---------------|---------|
| **Desktop app** | Native window | Yes | `python src/suzent/server.py` AND `cd src-tauri && npm run dev` |

> **Note**: For Windows users, you can simply run `start-tauri-dev.ps1` from the root directory.

## Prerequisites

### Required for All Development

- **Node.js** 20.x or higher
- **Python** 3.12 or higher

### Required for Desktop App Mode

- **Rust** 1.75 or higher
  ```bash
  # Windows
  winget install --id Rustlang.Rustup

  # Or download from https://rustup.rs/
  ```

### Platform-Specific Requirements

**Windows**
- Microsoft Visual C++ Build Tools
- WebView2 Runtime (usually pre-installed on Windows 10/11)

**macOS**
```bash
xcode-select --install
```

**Linux (Ubuntu/Debian)**
```bash
sudo apt-get update
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev \
  libappindicator3-dev librsvg2-dev patchelf
```

## Development Modes

### Desktop App Mode

Uses Tauri to create a native desktop window. Requires Rust.

**Terminal 1** - Start Python backend:
```bash
python src/suzent/server.py
```

Expected output:
```
INFO:     Starting Suzent server on http://127.0.0.1:8000
INFO:     Application startup complete.
```

**Terminal 2** - Start Tauri:
```bash
cd src-tauri
npm install
npm run dev
```

This will:
1. Start Vite dev server (frontend) on http://localhost:5173
2. Compile the Rust code (first time only, takes a few minutes)
3. Open a native desktop window
4. Frontend connects to backend on port 8000


## Configuration

### Development vs Production

| Config File | Mode | Backend |
|-------------|------|---------|
| `tauri.conf.json` | Development | External (port 8000) |
| `tauri.conf.prod.json` | Production | Bundled executable |

**Development mode** (`npm run dev`):
- No bundled backend - expects backend running on port 8000
- Frontend hot-reload enabled
- DevTools available (right-click in window)

**Production mode** (`npm run build`):
- Bundles Python backend as executable
- Backend auto-starts on dynamic port
- All assets bundled into single installer

### Environment Variables

The backend automatically detects bundled environment through:

| Variable | Purpose |
|----------|---------|
| `SUZENT_PORT` | Dynamically assigned port |
| `SUZENT_HOST` | Bound to `127.0.0.1` in production |
| `SUZENT_APP_DATA` | Application data directory |

### Tauri Configuration

Edit `src-tauri/tauri.conf.json` to customize:
- Window size and behavior
- Application name and version
- Bundle settings
- Security policies

## Hot Reload Behavior

| Component | Hot reload | Action on change |
|-----------|------------|------------------|
| Frontend (React) | Yes | Automatic |
| Backend (Python) | No | Restart manually |
| Rust code | No | Restart Tauri |

## Command Reference

| Task | Command |
|------|---------|
| Start backend | `python src/suzent/server.py` |
| Start Tauri dev | `cd src-tauri && npm run dev` |
| Start browser dev | `cd frontend && npm run dev` |
| Build full app | `cd src-tauri && npm run build:full` |
| Build backend only | `python scripts/build_backend.py` |
| Build Tauri only | `cd src-tauri && npm run build` |

## Troubleshooting

### Backend Issues

**"resource path doesn't exist" during `npm run dev`**

This is expected. Development mode does not use the bundled backend. Start the Python backend manually:
```bash
python src/suzent/server.py
```

**Backend not responding**

Verify backend is running:
```bash
curl http://localhost:8000/api/config
```
Should return JSON configuration.

### Rust/Tauri Issues

**"cargo: command not found"**

Install Rust from https://rustup.rs/ and restart your terminal.

**Cargo build fails**

Update Rust and clean the build:
```bash
rustup update
cd src-tauri && cargo clean
```

### Frontend Issues

**Frontend shows connection errors**

1. Verify backend is running: `curl http://localhost:8000/api/config`
2. Check browser console for the actual error
3. Ensure CORS is working (should be by default)

**Changes not appearing**

- Frontend changes: Should auto-reload. Try hard refresh (Ctrl+Shift+R).
- Backend changes: Restart the backend (Ctrl+C, then restart).
- Rust changes: Restart Tauri dev server.

### General Issues

**First build is very slow**

The first Rust build takes 5-10 minutes to compile all dependencies. Subsequent builds are faster due to caching.

---

For production builds, see [README_DESKTOP.md](./README_DESKTOP.md#production-build).
