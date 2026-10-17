# macOS release signing

The desktop workflow publishes raw Mach-O executables for the main app and the
installer, plus a disk image (`suzent-installer-macos-<arch>.dmg`) that the
landing page offers for download. Everything must be signed with a
**Developer ID Application** certificate, with hardened runtime and a secure
timestamp, and accepted by Apple's notary service before upload. An iOS Apple
Distribution certificate does not work here.

| Asset | Consumer |
| --- | --- |
| `suzent-macos-<arch>` | `setup.sh`, the installer, and `suzent update` |
| `suzent-installer-macos-<arch>` | `setup.sh` and `suzent update` (standalone updater) |
| `suzent-installer-macos-<arch>.dmg` | Browser downloads from the landing page |

Browsers drop the execute bit, so a downloaded raw executable appears as a
"Document" in Finder. The disk image contains `Suzent Installer.app`, which
users can double-click. Keep the raw asset names unchanged: older `setup.sh`
copies and installed CLIs download them by name.

The desktop build uses the existing `mobile-release` GitHub environment to share
the Apple notarization credentials with iOS. Configure these environment secrets:

| Secret | Value |
| --- | --- |
| `MACOS_CERTIFICATE_BASE64` | Base64-encoded `.p12` export containing the Developer ID Application certificate and private key |
| `MACOS_CERTIFICATE_PASSWORD` | Password for that `.p12` export |
| `APP_STORE_CONNECT_KEY_BASE64` | Base64-encoded App Store Connect API private key (`.p8`), shared with iOS |
| `APP_STORE_CONNECT_KEY_ID` | API key ID |
| `APP_STORE_CONNECT_ISSUER_ID` | API key issuer ID |

Configure this variable in the same environment:

| Variable | Value |
| --- | --- |
| `MACOS_SIGNING_IDENTITY` | Full identity, such as `Developer ID Application: Example (TEAMID)` |

`scripts/sign-macos-release.sh` imports the certificate into a temporary keychain,
signs both executables, submits a ZIP to `notarytool`, requires `Accepted`, and
checks each executable with `codesign -R="notarized" --check-notarization`.
`spctl --assess` targets app bundles and is not suitable for these raw executables. It restores the keychain search list and
removes the temporary credentials on exit. Missing credentials or verification
failures prevent the build from publishing its assets.

Raw executables cannot have a notarization ticket stapled to them. Gatekeeper
needs network access to retrieve their tickets.

### Installer disk image

When `MACOS_INSTALLER_APP`, `MACOS_INSTALLER_BINARY` and `MACOS_INSTALLER_DMG`
are set, the script also packages the installer:

1. Copies the Tauri bundle (`Suzent Installer.app`) and adds the signed
   standalone installer as `Contents/Helpers/suzent-installer`.
2. Signs the app bundle, builds a compressed HFS+ disk image with the app and an
   `Applications` link, and signs the disk image.
3. Submits the disk image to `notarytool` alongside the executable ZIP, so the
   two submissions wait in parallel.
4. Staples the ticket to the disk image, then requires `stapler validate`,
   `spctl --assess --type open --context context:primary-signature` for the
   disk image, and `spctl --assess --type execute` for the mounted app.

`MACOS_INSTALLER_BINARY` must be one of the executables passed to the script, so
the helper is byte-for-byte the published `suzent-installer-macos-<arch>`. The
installer copies its own executable to `~/.suzent/updater/suzent-installer`.
Inside an app, the main executable's signature is bound to the bundle's
`Info.plist`, so a copy taken out of `Contents/MacOS` fails verification. The
installer stages the `Contents/Helpers` copy instead.

The stapled ticket lets Gatekeeper accept the disk image offline. The
app inside it is covered by the same ticket once the disk image is mounted.

These changes apply to newly built assets. Rebuild an affected release with
`.release-assets-mode` set to `build`; `reuse` preserves the previous binaries,
including their signing status. Published releases cannot be rebuilt by this
workflow: prepare a new patch release to replace an unsigned published version.

See Apple's [notarization requirements](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

## Verify existing assets

Dispatch **Build and Publish Desktop Release** with an existing desktop tag and
`verify_signing=true`. This path verifies the published checksum of the main app
binary for each architecture. It builds the installer executable and app bundle
from the dispatched ref, because releases before the disk image do not contain
an app bundle. It then signs and notarizes the main app and installer
executables, and packages, notarizes and staples the installer disk image with
the same Gatekeeper checks as a release build. The job uploads the
`signed-macos-*` tar archives and the stapled `suzent-installer-macos-*.dmg` as
Actions artifacts for seven days. It does not modify the GitHub Release. Dispatch
it from a workflow branch to validate signing changes before merging them.

The verification job preserves the signed archive before waiting for Apple and
uploads it even when notarization times out or fails. An artifact alone is not
proof of notarization. Before distributing a preserved candidate, require
`codesign --verify --strict -R="notarized" --check-notarization` to succeed for
every executable, and `xcrun stapler staple` plus `stapler validate` to succeed
for the disk image. Do not re-sign the preserved files: doing so changes the code
signature and requires a new notarization submission.
