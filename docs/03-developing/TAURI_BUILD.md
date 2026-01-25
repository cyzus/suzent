# Production Build Guide

Guide for building SUZENT as a standalone desktop application for distribution.

For development setup, see [DEV_GUIDE.md](./DEV_GUIDE.md) instead.

## Prerequisites

### Build Tools

**All platforms:**
- Node.js 20.x or higher
- Python 3.12 or higher
- Rust 1.75 or higher (https://rustup.rs/)
- Nuitka for Python compilation:
  ```bash
  pip install nuitka orderedset zstandard
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

## Quick Build

Build the complete standalone application:

```bash
cd src-tauri
npm run build:full
```

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

## Build Artifacts

Find installers at:

| Platform | Location |
|----------|----------|
| Windows | `src-tauri/target/release/bundle/msi/SUZENT_x.x.x_x64_en-US.msi` |
| macOS | `src-tauri/target/release/bundle/dmg/SUZENT_x.x.x_x64.dmg` |
| Linux | `src-tauri/target/release/bundle/appimage/suzent_x.x.x_amd64.AppImage` |

## Manual Build Steps

If you prefer to build step by step:

### 1. Install Dependencies

```bash
cd src-tauri
npm install

cd ../frontend
npm install
cd ..
```

### 2. Build Frontend

```bash
cd frontend
npm run build
cd ..
```

### 3. Build Python Backend

```bash
python scripts/build_backend.py
```

Creates a standalone executable at `src-tauri/binaries/suzent-backend` (or `.exe` on Windows).

### 4. Build Tauri Application

```bash
cd src-tauri
npm run build
```

## Testing the Build

### Test Backend Executable

```bash
cd src-tauri/binaries

# Set required environment variables
export SUZENT_PORT=8000
export SUZENT_HOST=127.0.0.1
export SUZENT_APP_DATA=/tmp/suzent-test

# Windows: use 'set' instead of 'export'
# set SUZENT_PORT=8000

./suzent-backend  # or suzent-backend.exe on Windows
```

In another terminal:
```bash
curl http://localhost:8000/api/config
```

### Test Full Application

1. Install the generated package (MSI, DMG, or AppImage)
2. Run the application
3. Test core features:
   - Create and manage chats
   - Upload files
   - Configure API keys
   - Use memory features
   - Load custom skills

## Application Icons

Icons should be placed in `src-tauri/icons/`:
- `32x32.png`
- `128x128.png`
- `128x128@2x.png` (256x256)
- `icon.icns` (macOS)
- `icon.ico` (Windows)

Generate icons from a source image:
```bash
npx @tauri-apps/cli icon path/to/icon.png
```

## CI/CD

Automated builds are configured in `.github/workflows/build-desktop.yml` for:
- Ubuntu 22.04 (x86_64)
- Windows Latest (x86_64)
- macOS Latest (x86_64 and aarch64)

Builds are triggered on:
- Git tags matching `v*`
- Manual workflow dispatch

## Troubleshooting

### Nuitka Build Fails

**Missing dependencies:**
```bash
pip install -r requirements.txt
```

**Outdated Nuitka:**
```bash
pip install --upgrade nuitka
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

## Code Signing

For production distribution, you will need to set up code signing:

**macOS:**
- Apple Developer ID certificate
- Notarization through Apple

**Windows:**
- Code signing certificate from a trusted CA
- SignTool from Windows SDK

## Next Steps

1. **Create Application Icons**: Generate proper icons for all platforms
2. **Code Signing**: Set up code signing for macOS and Windows
3. **Auto-Updates**: Implement Tauri's built-in updater
4. **Optimize Bundle Size**: Selectively include only necessary Playwright binaries
5. **Test Cross-Platform**: Test on all target platforms

## Modified Files for Tauri Support

**Backend:**
- `src/suzent/server.py` - Dynamic port/host from environment variables
- `src/suzent/config.py` - Bundled environment detection

**Frontend:**
- `frontend/src/lib/api.ts` - Tauri detection and dynamic API base URL
- `frontend/src/hooks/useChatStore.tsx` - Updated API calls
- `frontend/src/hooks/usePlan.ts` - Updated API calls
- `frontend/src/vite-env.d.ts` - TypeScript definitions

**New Files:**
- `src-tauri/` - Entire Tauri project structure
- `scripts/build_backend.py` - Nuitka build script
- `scripts/build_tauri.sh` - Unix build script
- `scripts/build_tauri.ps1` - Windows build script
- `.github/workflows/build-desktop.yml` - CI/CD pipeline

## Resources

- [Tauri Documentation](https://v2.tauri.app/)
- [Nuitka Documentation](https://nuitka.net/doc/user-manual.html)
- [Embedding External Binaries in Tauri](https://v2.tauri.app/develop/sidecar/)
