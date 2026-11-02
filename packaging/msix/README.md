# MSIX (Microsoft Store) package

The Store build is the normal Tauri app plus a relocatable Python runtime with
Suzent installed in it. The Tauri exe detects this layout and runs in
**packaged mode** (`src-tauri/src/packaged.rs`).

## Layout

```text
pkg\
  AppxManifest.xml            rendered from AppxManifest.template.xml
  suzent.exe                  Tauri release exe (built with tauri.conf.store.json)
  Assets\                     StoreLogo / Square44x44 / Square150x150 (from src-tauri/icons)
  runtime\python\             python-build-standalone CPython 3.12 + locked deps + suzent
  app\config\  app\skills\  app\plugins\   tracked repo files (SUZENT_PROJECT_DIR)
```

In packaged mode the app:

- starts `runtime\python\python.exe -m suzent.server` with
  `SUZENT_PROJECT_DIR=<pkg>\app`, `PYTHONDONTWRITEBYTECODE=1` and `PYTHONNOUSERSITE=1`;
- keeps all writable state in `~/.suzent` (also `PLAYWRIGHT_BROWSERS_PATH` and
  `UV_CACHE_DIR`, because `%LOCALAPPDATA%` is virtualized per package);
- attaches only to backends that report `source_root: null`;
- disables the self-updater and installer ("updated through the Microsoft Store");
- implements the Settings > Background service toggle with the package's
  `StartupTask` (`TaskId="SuzentStartup"`, disabled by default).

## Manifest placeholders

| Placeholder | Value | CI source (repo variable) |
|---|---|---|
| `{{IDENTITY_NAME}}` | Partner Center Package/Identity/Name | `MSIX_IDENTITY_NAME` |
| `{{PUBLISHER}}` | Partner Center Package/Identity/Publisher (`CN=...`) | `MSIX_PUBLISHER` |
| `{{PUBLISHER_DISPLAY_NAME}}` | Partner Center PublisherDisplayName | `MSIX_PUBLISHER_DISPLAY_NAME` |
| `{{VERSION}}` | app version + `.0`, e.g. `0.20.0.0` | `src-tauri/tauri.conf.json` |

## Building locally

The CI workflow (`.github/workflows/msix.yml`) is the reference. By hand, on Windows:

1. `uv python install 3.12` and copy that interpreter dir to `pkg\runtime\python`.
2. `uv export --frozen --no-dev --extra social --extra camera --no-editable --no-hashes --no-emit-project > req.txt`
   (the built-in plugins' extras must be bundled: the package has no `uv.lock`
   or writable environment to install them into later), then
   `uv pip install --python pkg\runtime\python\python.exe --break-system-packages -r req.txt`
   and `uv pip install --python ... --break-system-packages --no-deps .`.
3. Delete the files that make signtool fail (`DLLs\tcl86t.dll`, `DLLs\tk86t.dll`,
   `vcruntime140.dll`, `vcruntime140_1.dll`) together with `tcl\`, `Lib\tkinter`,
   `Lib\idlelib`, `Lib\turtledemo`, `DLLs\_tkinter.pyd`; then `python -m compileall -q`.
4. Copy `config\`, `skills\` and `plugins\` (tracked files only) to `pkg\app\`.
5. `cd src-tauri; npx tauri build --no-bundle --config tauri.conf.store.json` and copy
   `target\release\suzent.exe` to `pkg\`.
6. Render the manifest, then either `makeappx pack /d pkg /p Suzent.msix /o`, or for a
   quick test with Developer Mode on: `Add-AppxPackage -Register pkg\AppxManifest.xml`.

To run a test build next to an existing Suzent, give it its own identifier
(a copy of `tauri.conf.store.json` with another `identifier`), its own manifest
`Identity Name`, and its own data dir by building with the environment variable
`SUZENT_DATA_DIR_NAME=.suzent-preview`.
