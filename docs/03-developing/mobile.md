# Native mobile clients

## Architecture decision

Suzent mobile uses SwiftUI on iOS and Kotlin/Jetpack Compose on Android. Both
applications live in this monorepo; Python remains managed by uv, Android by
Gradle, and iOS by Xcode/Swift Package Manager. Existing desktop paths stay intact.
The clients share a wire contract and fixtures, not a cross-platform UI runtime.

The desktop backend owns agent execution, memory and chat history. Mobile has two
independent roles: a remote client and an opt-in foreground device Node. A Node
grant does not authorize HTTP access. No Python runtime runs on the phone.

## Status and roadmap

The first increment is a developer preview, not a release-ready mobile product. What it
covers is described under [Run](#run) and [Preview flow](#preview-flow); what it does not
is under [Limits](#limits).

Mobile uses a separate, revocable client credential issued after desktop approval.
In desktop Settings → Devices → Mobile access, generate a short-lived QR invitation.
Scan it in the native app (or paste the invitation), confirm the backend address,
compare the displayed code, and approve the required conversations and actions.
Host and peer-agent tokens are not accepted as mobile credentials. Existing preview
connections must pair again. See the [pairing contract](../../packages/mobile-contract/pairing.md).

Planned, in order:

1. **Interactive tools and attachments** — scoped upload and mobile tool-approval UI.
2. **Device capabilities** — user-confirmed camera capture and upload, audio capture,
   single location fix; native permission and lifecycle adapters.
3. **Resilience** — durable event cursor/replay, idempotent send IDs in the backend, local
   outbox and transcript cache, endpoint migration, retry/backoff, device command
   deadlines and deduplication. Current sends are never retried automatically.
4. **System integration** — share extensions/intents, opt-in APNs/FCM notification
   delivery, platform-specific background work, accessibility and device QA.

## Layout

```
apps/ios/                 SwiftUI app + XcodeGen project specification
apps/android/             Compose app + Gradle project
packages/mobile-contract/ Protocol description and cross-language fixtures
packages/SuzentCore/       Foundation-only Swift protocol/client package
```

## Run

Use a backend with mobile pairing/client protocol 1 and snapshot/cursor protocol 1.
The phone checks capabilities before connecting and reports incompatible versions.

Enable desktop **Reachable by other devices**, restart, and use its LAN/Tailscale
address on port 25314 (never the phone's localhost) in the desktop pairing card.
Pair the phone and select its permissions on desktop. HTTPS/WSS is required for release builds. Debug builds
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

1. Pair with the desktop and open a shared chat. New conversations require the
   corresponding permission; send and stop permissions are independent. The
   phone’s **Access** page shows the grant and the separate Node controls.
2. Send text. `/mobile/client/send` starts work on the backend, independently of the screen.
   `/mobile/client/live` supplies transient text; the persisted transcript is authoritative.
   Mobile uses `protocol: 1`, sharing desktop's authoritative snapshots and
   sequence cursors. Reconnects resume from the last applied event, deduplicate
   retransmissions and replace transient text when a fresh snapshot arrives.
   `STREAM_END` confirms persistence; the received response stays visible until
   saved history has loaded. See [Stream recovery](stream-recovery-protocol.md).
The native clients subscribe immediately after send acknowledgment, showing the
accepted user message locally while the backend remains authoritative. Live text
is published in 50 ms batches, with a final flush on completion or failure.
Android parses Markdown off the UI thread and memoizes the saved transcript's
presentation. The scoped title index does not load transcripts/checkpoints;
mobile detail reads omit desktop context-budget computation and return current
`isRunning` state. Completion reconciles that state in both the selected chat and
list so the stop control cannot retain a stale list flag.

3. On foreground return, refresh the transcript. A dropped stream does not
   automatically resend the message. A lost send acknowledgment has an unknown
   outcome: inspect history before sending again.
4. Enable Node separately, then approve its pairing code on the desktop.
   Invoke `device.status` from the desktop to verify the phone role.
5. Backgrounding disconnects Node. Foregrounding reconnects an enabled Node.
   Disabling Node closes the connection but retains its pairing credential.
   Forgetting the connection removes local credentials; revoke remotely on desktop.

## Limits

The preview renders Markdown replies and structured tool/reasoning activities in
expandable native views. Tool approvals, attachments, citations, A2UI and some
legacy inline tool formats still require desktop. Shared palette and filtering
rules live in `packages/presentation`; regenerate platform files with
`uv run python scripts/generate_presentation.py` after editing their source.
It lists up to 1,000 conversations permitted by the device grant. Replay is bounded and in-memory; it is not a durable
event cursor or an always-online phone. An observer reconnects up to five times with capped backoff. Mutation requests
are never automatically retried. Exhausted recovery preserves received text.

### Test coverage

Both platforms test protocol/URL validation and shared display/recovery fixtures.
Android additionally tests authenticated HTTP/SSE, safe GET recovery, no mutation
retries and interrupted-observer cursor recovery. The
backend side covers independent observers, disconnection, overflow recovery, and
snapshot handoff, terminal save confirmation and compatibility with legacy clients. Desktop TypeScript checks
and its display tests run in the same suite.

Not covered, and required before any release: physical-device lifecycle, TLS, Node pairing,
and end-to-end concurrent generation. Full native builds and simulator/device smoke tests
are release gates in addition to the protocol unit tests — CI definitions do not imply a
successful remote run.

Manual matrix, to run on both platforms: denied/revoked tokens; wrong address; background
during generation; return after completion; stopped task; lost send acknowledgment; Node
pending/approved/rejected; capability invocation; background disconnect; forget/re-pair;
TLS failure. Never put real credentials into fixtures or logs.

### Running the iOS simulator

For an interactive simulator run, keep local signing enabled so Keychain works:

```sh
xcodegen generate --spec apps/ios/project.yml
xcodebuild -project apps/ios/Suzent.xcodeproj -scheme Suzent \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/suzent-ios-build CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES build
```

Unsigned CI builds check compilation only; launching an unsigned app can fail
Keychain access. The simulator uses the same pairing flow as a physical device.
For a backend on the same Mac, generate an invitation for `http://127.0.0.1:25314`
and paste it into the simulator app. HTTP is debug-only. Simulator cameras may be
unavailable; paste uses the same protocol and operator approval as camera scanning.

### Visual foundation

Both native apps use the desktop palette, square outlines, 2-unit borders and hard
shadows. Shared spacing and type-scale constants also live in
`packages/presentation/tokens.json`. Pairing, conversations, chat and access are
separate views. Both apps use the centered SUZENT wordmark, blue primary actions,
flat conversation rows and an outlined composer. Assistant messages carry the
robot badge; inline code uses yellow highlights and top-level code blocks have
black language headers with horizontally scrollable light bodies. User messages
use a neutral surface so yellow retains its emphasis role. Keyboard and camera
permission prompts stay native. iOS uses VisionKit QR recognition; Android uses ZXing embedded. Neither
scanner saves an image. Both apps provide English and Simplified Chinese strings.
