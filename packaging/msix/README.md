# MSIX (Microsoft Store) package

The Store build is the normal Tauri app plus a relocatable Python runtime with
Suzent installed in it. The Tauri exe detects this layout and runs in
**packaged mode** (`src-tauri/src/packaged.rs`).

## Layout

```text
pkg\
  AppxManifest.xml            rendered from AppxManifest.template.xml
  suzent.exe                  Tauri release exe (built with tauri.conf.store.json)
  Assets\                     StoreLogo / Square44x44 / Square150x150 (from src-tauri/icons),
                              plus unplated Square44x44 targetsize icons (from packaging/msix/assets)
  resources.pri               makepri index of Assets; without it the shell ignores the
                              unplated icons and draws the logo on an accent-coloured plate
  runtime\python\             python-build-standalone CPython 3.12 + locked deps + suzent
  app\config\  app\skills\  app\plugins\  app\extensions\browser\   tracked repo files (SUZENT_PROJECT_DIR)
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

## Icons

`assets\` holds `Square44x44Logo.targetsize-<n>_altform-unplated.png` and
`..._altform-lightunplated.png` for sizes 16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96
and 256, each a Lanczos downscale of `src-tauri/icons/icon.png`. Regenerate them when the app
icon changes.

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
4. Copy `config\`, `skills\`, `plugins\` and `extensions\browser\` (tracked files only)
   to `pkg\app\`. The browser extension is served from there by Settings > Browser.
5. `cd src-tauri; npx tauri build --no-bundle --config tauri.conf.store.json` and copy
   `target\release\suzent.exe` to `pkg\`.
6. Render the manifest, copy `packaging\msix\assets\*.png` into `pkg\Assets\`, and build
   `pkg\resources.pri` with `makepri` as the Pack step in `msix.yml` does. Then either `makeappx pack /d pkg /p Suzent.msix /o`, or for a
   quick test with Developer Mode on: `Add-AppxPackage -Register pkg\AppxManifest.xml`.

To run a test build next to an existing Suzent, give it its own identifier
(a copy of `tauri.conf.store.json` with another `identifier`), its own manifest
`Identity Name`, and its own data dir by building with the environment variable
`SUZENT_DATA_DIR_NAME=.suzent-preview`.

## Publishing to the Microsoft Store

The `publish` job in `msix.yml` submits the built package with the
[Microsoft Store Developer CLI](https://learn.microsoft.com/en-us/windows/apps/publish/msstore-dev-cli/github-actions)
(`microsoft/microsoft-store-apppublisher`, then `msstore reconfigure` and
`msstore publish <msix> -id 9MZQ1HHXHVZT`). It downloads the artifact from the
build job, so the package it submits is the one that passed the smoke test.

**Environment and secrets.** The job runs in the GitHub Environment
`microsoft-store` and is the only job that reads these secrets:

| Secret | Value |
|---|---|
| `AZURE_AD_TENANT_ID` | Entra ID tenant linked to Partner Center |
| `AZURE_AD_APPLICATION_CLIENT_ID` | Client ID of the Entra app added in Partner Center (User management > Microsoft Entra applications, Manager role) |
| `AZURE_AD_APPLICATION_SECRET` | A client secret of that app |
| `SELLER_ID` | Partner Center Seller ID (Account settings > Legal info) |

Restrict the environment's deployment branches and tags to `main` and `v*`,
and add required reviewers if every submission should be approved by hand. The
repo variables `MSIX_IDENTITY_NAME`, `MSIX_PUBLISHER` and
`MSIX_PUBLISHER_DISPLAY_NAME` must hold the Partner Center identity; the job
refuses to publish the CI test identity.

**Triggers.**

- A desktop release: `release-on-merge.yml` tags `vX.Y.Z` and dispatches
  `msix.yml` on that tag with `publish=true`. Pushing a `v*` tag by hand also
  publishes.
- By hand: `gh workflow run msix.yml --ref vX.Y.Z -f publish=true` (or from
  `main`). Without `-f publish=true` a manual run only builds and smoke-tests.
- Pull requests and branch pushes never publish.

**Versions.** The manifest version is the app version from
`src-tauri/tauri.conf.json` plus `.0` (the Store requires the fourth part to be
0, and each submission must be higher than the last). On a tag, the build fails
before doing any work if the tag is not `v<app version>`. Re-running a publish
for a version the Store already has will be rejected by Partner Center.

**After submission.** The Store still certifies every submission. For a second
gate, set the submission option *Publish this submission manually* (Partner
Center > the app > Pricing and availability > Publishing) so a certified
build waits until someone releases it. Runs never overlap: the publish job
uses the `msstore-publish` concurrency group and is never cancelled.