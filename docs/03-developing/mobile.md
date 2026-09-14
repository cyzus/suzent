# Native mobile clients

## Architecture decision

Suzent mobile uses SwiftUI on iOS and Kotlin/Jetpack Compose on Android. Both
applications live in this monorepo; Python remains managed by uv, Android by
Gradle, and iOS by Xcode/Swift Package Manager. Existing desktop paths stay intact.
The clients share a wire contract and fixtures, not a cross-platform UI runtime.

The desktop backend owns agent execution, memory and chat history. Mobile has two
independent roles: a remote client and an opt-in foreground device Node. A Node
grant does not authorize HTTP access. No Python runtime runs on the phone.

## Delivery plan

1. **Foundation (this increment):** native projects, secure credential storage,
   explicit backend address, remote-host token login, chat list/create/load,
   background turn submission with live text, stop, foreground refresh, and
   independently paired foreground Node exposing `device.status`.
2. **Mobile authorization:** operator-approved short-lived QR bootstrap, a
   resource-scoped client grant, protocol/version negotiation, scoped attachment
   upload and client approval UI. Do not silently broaden Node or agent grants.
3. **Useful device capabilities:** user-confirmed camera capture and upload,
   audio capture, single location fix; native permission and lifecycle adapters.
4. **Resilience:** durable event cursor/replay, idempotent send IDs in the backend,
   local outbox and transcript cache, endpoint migration, retry/backoff, device
   command deadlines and deduplication. Current sends are never retried automatically.
5. **System integration:** share extensions/intents, opt-in APNs/FCM notification
   delivery, platform-specific background work, accessibility and device QA.

The first increment is a developer preview, not a release-ready mobile product.
It deliberately uses existing full-access host tokens: the user must create one
in desktop Settings → Devices → Remote host access. This permits administration
of the backend, even though the preview UI only uses chat endpoints. Peer agent
grants are not a substitute: they use unattended peer-agent semantics and do not
provide a full interactive client session.

## Layout

```
apps/ios/                 SwiftUI app + XcodeGen project specification
apps/android/             Compose app + Gradle project
packages/mobile-contract/ Protocol description and cross-language fixtures
packages/SuzentCore/       Foundation-only Swift protocol/client package
```

## Run

Enable desktop **Reachable by other devices**, restart, and use its LAN/Tailscale
address on port 25314 (never the phone's localhost). Create a revocable host token
and enter it in the app. HTTPS/WSS is required for release builds. Debug builds
allow explicit HTTP addresses for a trusted LAN/tailnet; HTTP is not encrypted.
No certificate-validation bypass or automatic URL redirect is supported.

### iOS

Install full Xcode and XcodeGen. From `apps/ios`, run `xcodegen generate`, open
`Suzent.xcodeproj`, choose a signing team and run the Suzent scheme. The generated
project is disposable; edit `project.yml`. iOS 17+ is required. Set a unique bundle
identifier and signing configuration for distribution. Tokens use a
device-only Keychain item; no credentials are stored in UserDefaults.

Run the Foundation protocol tests with the Swift testing frameworks from Xcode:

```sh
swift test --package-path packages/SuzentCore
```

Command Line Tools alone can build the core package (`swift build --package-path
packages/SuzentCore`), but some installations lack the complete Testing framework
needed by `swift test`.

### Android

Install JDK 17 and Android SDK 36. Open `apps/android` in Android Studio or run
`./gradlew :app:assembleDebug :app:testDebugUnitTest`. Android 8/API 26+ is required.
Tokens are encrypted with an Android Keystore AES-GCM key; app backup is disabled.

### Preview flow

1. Connect with backend origin and host token; create or open a chat.
2. Send text. `/chat/send` starts work on the backend, independently of the screen.
   `/chat/live` supplies transient text; the persisted transcript is authoritative.
   Mobile sends `replay: true` to receive an independent bounded replay queue.
   Default requests preserve the desktop's existing consume-once reconnect
   semantics. A slow subscriber or truncated replay receives `REPLAY_UNAVAILABLE`
   and must refresh persisted history. This is
   in-memory replay for the current turn, not a durable event cursor.
3. On foreground return, refresh the transcript. A dropped stream does not
   automatically resend the message. A lost send acknowledgment has an unknown
   outcome: inspect history before sending again.
4. Enable Node separately, then approve its pairing code on the desktop.
   Invoke `device.status` from the desktop to verify the phone role.
5. Backgrounding disconnects Node. Foregrounding reconnects an enabled Node.
   Disabling Node closes the connection but retains its pairing credential.
   Forgetting the connection removes local credentials; revoke remotely on desktop.

## Limits and verification

The preview renders Markdown replies and structured tool/reasoning activities in
expandable native views. Tool approvals, attachments, citations, A2UI and some
legacy inline tool formats still require desktop. Shared palette and filtering
rules live in `packages/presentation`; regenerate platform files with
`uv run python scripts/generate_presentation.py` after editing their source.
It lists the latest 50 chats. Replay is bounded and in-memory; it is not a durable
event cursor or an always-online phone. An in-flight connection has no automatic retry loop; refresh
or foreground the app to reconnect. Full native builds and simulator/device smoke
tests are required before release, in addition to protocol unit tests.

Test on both platforms: denied/revoked tokens; wrong address; background during
generation; return after completion; stopped task; lost send acknowledgment;
Node pending/approved/rejected; capability invocation; background disconnect;
forget/re-pair; TLS failure. Never put real credentials into fixtures or logs.

### Verified checks

- Android Debug build and eight JVM tests pass, covering protocol/URL validation,
  authenticated HTTP/SSE, safe GET recovery, no mutation retries, and six shared
  display fixtures. Real backend history and tool cards were inspected on Android 35.
- iOS builds with Xcode 26.6 and runs on the iOS 26.5 iPhone 17 Pro simulator.
  All five Swift core tests pass, including the shared display fixtures. Real
  backend history and expandable tool output were inspected without starting a run.
- Desktop TypeScript checks and 19 display tests pass; its production build was
  also verified during shared-presentation implementation.
- 24 focused backend tests pass, including independent observers, disconnection,
  overflow recovery, and preserving desktop unread position during mobile replay.
- Physical-device lifecycle, TLS, Node pairing, and end-to-end concurrent generation
  still need broader QA. CI definitions do not imply a successful remote run.

### Running the iOS simulator

For an interactive simulator run, keep local signing enabled so Keychain works:

```sh
xcodegen generate --spec apps/ios/project.yml
xcodebuild -project apps/ios/Suzent.xcodeproj -scheme Suzent \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/suzent-ios-build CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES build
```

Unsigned CI builds check compilation only; launching an unsigned app can fail
Keychain access. Debug simulator builds accept an empty host token only for exact
loopback origins (`127.0.0.1`, `::1`, `localhost`), matching the backend's existing
trusted local access policy. Enter `http://127.0.0.1:25314` to preview the backend
on the same Mac. Physical devices, non-loopback origins and Release builds still
require a host token. No server authentication policy is changed.
