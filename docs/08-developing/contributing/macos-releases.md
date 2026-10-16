# macOS release signing

The desktop workflow publishes raw Mach-O executables for the main app and the
installer. Both must be signed with a **Developer ID Application** certificate,
with hardened runtime and a secure timestamp, and accepted by Apple's notary
service before upload. An iOS Apple Distribution certificate does not work here.

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
needs network access to retrieve their tickets. An offline-friendly release
would need a stapled app bundle, DMG, or installer package.

These changes apply to newly built assets. Rebuild an affected release with
`.release-assets-mode` set to `build`; `reuse` preserves the previous binaries,
including their signing status. Published releases cannot be rebuilt by this
workflow: prepare a new patch release to replace an unsigned published version.

See Apple's [notarization requirements](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

## Verify existing assets

Dispatch **Build and Publish Desktop Release** with an existing desktop tag and
`verify_signing=true`. This path verifies the published checksums, signs and
notarizes the existing Intel and Apple Silicon binaries, then uploads
`signed-macos-*` tar archives as Actions artifacts for seven days. It does not
modify the GitHub Release. This also allows validation from a workflow branch
before merging the signing changes.
