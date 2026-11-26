# MSIX (Microsoft Store) package

The Store build is the Electron desktop app (`apps/desktop`) unpacked, with the
same bundled Python runtime the installers ship, plus a small `suzent.exe`
helper (`apps/desktop/store-cli`). Electron reports `process.windowsStore`
inside the package, and the app behaves as a Store install.

## Layout

```text
pkg\
  AppxManifest.xml            rendered from AppxManifest.template.xml
  SUZENT.exe                  Electron app (electron-builder --dir, win-unpacked)
  Assets\                     StoreLogo / Square44x44 / Square150x150 and the unplated
                              Square44x44 targetsize icons (all from packaging/msix/assets)
  resources.pri               makepri index of Assets; without it the shell ignores the
                              unplated icons and draws the logo on an accent-coloured plate
  resources\app.asar          the Electron shell and web UI
  resources\runtime\python\   CPython 3.12 + locked deps + suzent (scripts/build_desktop_runtime.py)
  resources\suzent\           config/ skills/ plugins/ extensions/browser (SUZENT_PROJECT_DIR)
  resources\bin\suzent.exe    store-cli: the `suzent` alias and the start-at-login switch
```

In the package the app:

- runs the backend from `resources\runtime\python` exactly as the installed app
  does, keeping all writable state in `~/.suzent` (`%LOCALAPPDATA%` is
  virtualized per package, so the Playwright and uv caches live there too);
- never updates itself: the Store does ("updated through the Microsoft Store");
- implements Settings > Background service with the package's `StartupTask`
  (`TaskId="SuzentStartup"`, off by default), switched by
  `resources\bin\suzent.exe --startup-task enable|disable|status`, because only
  a process inside the package may change it;
- offers the `suzent` command through the execution alias, which points at the
  same helper; it runs `python -m suzent.cli` with the app's environment and
  refuses `update`, `upgrade` and `repair`.

Store users of the earlier Tauri package update to this one like any other
version: the Identity Name, Publisher and `Application Id="App"` are unchanged,
so data in `~/.suzent` and Start pins carry over.

## Icons

`assets\` holds `Square44x44Logo.targetsize-<n>_altform-unplated.png` and
`..._altform-lightunplated.png` for sizes 16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96
and 256, each a Lanczos downscale of the app icon (`apps/desktop/icons/icon.png`), next to
`StoreLogo.png`, `Square44x44Logo.png` and `Square150x150Logo.png`. Regenerate them when
the app icon changes.

## Manifest placeholders

| Placeholder | Value | CI source (repo variable) |
|---|---|---|
| `{{IDENTITY_NAME}}` | Partner Center Package/Identity/Name | `MSIX_IDENTITY_NAME` |
| `{{PUBLISHER}}` | Partner Center Package/Identity/Publisher (`CN=...`) | `MSIX_PUBLISHER` |
| `{{PUBLISHER_DISPLAY_NAME}}` | Partner Center PublisherDisplayName | `MSIX_PUBLISHER_DISPLAY_NAME` |
| `{{VERSION}}` | app version + `.0`, e.g. `0.20.0.0` | `apps/desktop/package.json` |

## Building locally

The CI workflow (`.github/workflows/msix.yml`) is the reference. By hand, on Windows:

1. Build the web UI (`cd frontend; npm ci; npm run build`), then the runtime:
   `uv run --no-project python scripts/build_desktop_runtime.py`.
2. `cd apps/desktop; npm ci; npm run dist:dir`, and copy `release\win-unpacked` to `pkg\`.
3. `cd apps/desktop/store-cli; cargo build --release`, and copy `target\release\suzent.exe`
   to `pkg\resources\bin\`.
4. Delete `vcruntime140.dll` and `vcruntime140_1.dll` from `pkg\resources\runtime\python`
   (signtool rejects them; the VCLibs framework dependency provides them).
5. Render the manifest, copy `packaging\msix\assets\*.png` into `pkg\Assets\`, and build
   `pkg\resources.pri` with `makepri` as the Pack step in `msix.yml` does. Then either
   `makeappx pack /d pkg /p Suzent.msix /o`, or for a quick test with Developer Mode on:
   `Add-AppxPackage -Register pkg\AppxManifest.xml`.

To run a test build next to an existing Suzent, give the manifest its own
`Identity Name` and the app its own data dir with the environment variable
`SUZENT_DATA_DIR`.

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
`apps/desktop/package.json` plus `.0` (the Store requires the fourth part to be
0, and each submission must be higher than the last). On a tag, the build fails
before doing any work if the tag is not `v<app version>`. Re-running a publish
for a version the Store already has will be rejected by Partner Center.

**After submission.** The Store still certifies every submission. For a second
gate, set the submission option *Publish this submission manually* (Partner
Center > the app > Pricing and availability > Publishing) so a certified
build waits until someone releases it. Runs never overlap: the publish job
uses the `msstore-publish` concurrency group and is never cancelled.

**Testers first.** To send releases to a Partner Center package flight instead
of everyone, create the flight in Partner Center and set its ID as the
`MSIX_FLIGHT_ID` repository variable; a manual run can also pass `flight_id`.
Clear the variable to ship to everyone again. Use this for the first Electron
package, so a few people check that the update from the Tauri package keeps
their data and pins.
