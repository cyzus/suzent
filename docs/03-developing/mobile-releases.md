# Mobile release distribution

Mobile releases are independent of desktop releases. Prepare a mobile release with
**Prepare Release → mobile**, review `release/mobile`, and merge after CI passes.
The merge workflow validates the release plan, creates an immutable `mobile-vX.Y.Z`
tag at the merge commit, and dispatches **Release mobile** against that tag for **Android only**.
Manual runs can choose `android`, `ios`, or `both`; Android is the default.
iOS can be uploaded later using the same tag with `platforms=ios`, without
rebuilding Android or modifying its published assets.
Tag pushes alone do not publish: the explicit dispatch also works with GitHub's
built-in token, whose tag pushes do not trigger another workflow.

## Configure once

Create a GitHub environment named `mobile-release`. Restrict deployments to `main`
(the dispatch workflow runs from main and checks out the immutable release SHA).
Use required reviewers if you want approval before signing and uploading.
Never commit signing keys, profiles, or passwords. Back up the Android signing key:
losing it can prevent upgrading APK installations.

Environment secrets:

| Name | Value |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Base64 of the persistent Android release keystore |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_ALIAS` | Release signing alias |
| `ANDROID_KEY_PASSWORD` | Alias password |
| `IOS_CERTIFICATE_BASE64` | Base64 of an Apple Distribution certificate **including its private key**, exported as P12 |
| `IOS_CERTIFICATE_PASSWORD` | P12 password (nonempty) |
| `IOS_PROFILE_BASE64` | Base64 of an App Store distribution profile for `com.suzent.mobile`, matching the certificate and team |
| `APP_STORE_CONNECT_KEY_BASE64` | Base64 of the App Store Connect team API key P8 |
| `APP_STORE_CONNECT_KEY_ID` | API key ID |
| `APP_STORE_CONNECT_ISSUER_ID` | API key issuer ID |

Environment variable `APPLE_TEAM_ID` holds the Apple developer team ID. Create the
`com.suzent.mobile` app in App Store Connect before the first upload and give the
API key permission to upload builds. Only the selected platforms require credentials. Missing configuration fails the relevant job;
there is no fallback to debug signing or an unsigned public artifact. Expired or
mismatched Apple credentials must be renewed before retrying.

The release runner uses macOS 26 and explicitly selects Xcode 26.3; the script
rejects iOS SDKs older than 26, matching the
[App Store upload requirement](https://developer.apple.com/news/upcoming-requirements/?id=04282026a).

The iOS job imports credentials into a temporary keychain, installs the supplied
profile, builds a Release device archive, and uses Xcode's `app-store-connect`
upload destination. It removes the imported keychain, profile, and decoded secrets
on exit. Only dSYM files are retained as Actions artifacts, not signing material.

## Outputs and numbering

- Android: release APK, AAB, and SHA256SUMS in the versioned GitHub Release.
- iOS: a build uploaded to App Store Connect; dSYMs retained as Actions artifacts.
- GitHub publication requires Android success and, when selected, iOS success.
  A deliberately skipped iOS job does not block Android; a failed iOS job does.
  An iOS-only run uploads to App Store Connect and does not publish GitHub assets. Mobile releases use
  `--latest=false` and do not replace the desktop latest release.
- Upload completion is not Apple processing, beta review approval, or App Store
  publication. Configure TestFlight testing groups and required review information
  in App Store Connect. Play Store upload/submission remains manual using the AAB.

Release build numbers are `100000 + packages/mobile-contract/version.json.build`.
Release planning increments that source counter. Both platforms get the same
number and reruns of the same tag keep it. Debug CI keeps its existing
`1000 + github.run_number` sequence; it is a different signing channel. Never
reset the source counter, reuse a release version, or mix debug APKs into the
public update channel. The first transition from debug to release Android signing
requires uninstalling the debug app and pairing again; subsequent APK releases
must use the same persistent key and preserve app data.

Before Play distribution, decide how the Play App Signing key relates to the APK
signing key. An upload key is not necessarily the key signing apps delivered by
Play. If those signatures differ, users cannot move between distribution channels
by an ordinary in-place update.

## Recovery

For a failed run, use **Re-run failed jobs**. Successful jobs and their outputs are
reused, avoiding another upload of an already accepted iOS build. If Apple accepted
an upload but the job failed afterward, check App Store Connect before retrying;
do not blindly rerun the upload or increment build numbers outside release planning.
Resolve the remaining artifact/job issue, or prepare a new release if another
binary must be uploaded. Full reruns after a successful Apple upload are not
idempotent and may be rejected as duplicate builds.

To retry tag creation/dispatch, rerun **Start Mobile Release After Merge**. It
accepts an existing tag only when it points to the same merge commit. To restart a
release that has not uploaded successfully, run **Release mobile** manually from
main with the existing tag. Tags outside main, tags mismatching the version source,
and missing mobile changelog entries are rejected. Published GitHub release assets
are never overwritten; draft assets may be replaced during recovery.

## Required first-release checks

Use the signed Release builds, not the debug builds, for acceptance:

- Pair over local trusted HTTPS and a remote HTTPS address; reject changed trust.
- Cancel/timeout on wrong Wi-Fi, desktop shutdown, or rejected permissions.
- Re-pair the same installation and revoke credentials from desktop.
- Send, stop, approve tools, background/foreground, and recover a running stream.
- Upgrade a signed Android release and a TestFlight build without losing pairing.
- Check iOS selection overlay, long names, large text, dark mode, and VoiceOver.
- Confirm the privacy/support pages, permission explanations, store screenshots,
  and a reviewable backend connection/demo before requesting store review.

The automation can be tested without production credentials using a throwaway
Android signing key. Such APKs must never be installed over or distributed as a
production release. Apple distribution must still be validated with the configured
team and App Store Connect account.
