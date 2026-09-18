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
In desktop Settings → Devices → Mobile access, choose the shared conversations
and actions, then generate a short-lived QR invitation. Scan it in the native app
(or paste the invitation), review the desktop name and server-provided permissions,
and confirm the connection on the phone. There is no second desktop approval.
Closing the QR cancels an unused invitation; issued device credentials can be
revoked separately. Abrupt desktop termination or network loss falls back to the
five-minute invitation expiry. Old invitations retain the code-comparison flow.
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
The QR includes the preferred origin plus discovered LAN/Tailscale candidates.
Updated phones check candidate capabilities without credentials, then display the
first reachable compatible address for confirmation. A three-second timeout per
candidate bounds this check. Old single-origin invitations remain supported.
Select permissions on desktop, then pair and confirm on the phone. Saved connections retain
only the confirmed address; changing networks does not migrate credentials.
HTTPS/WSS is required for release builds. Debug builds
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
expandable activity rails. Attachments, citations, A2UI and some
legacy inline tool formats still require desktop. Shared palette and filtering
rules live in `packages/presentation`; regenerate platform files with
`uv run python scripts/generate_presentation.py` after editing their source.
Mobile logo geometry is generated from `frontend/public/favicon.svg`, including
the perspective-projected eyes on the animated start-page cube.
Both launchers use the approved white-background cube-and-hand artwork in
`packages/presentation/assets/mobile-icon.png`. Regenerate their opaque PNGs with
`uv run python scripts/generate_app_icons.py` on macOS (uses `sips`). Android keeps
the artwork inside the adaptive icon safe area and retains the canonical eyes
for its monochrome themed icon. The in-app logo remains generated from the SVG.
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

### Mobile tool approvals and activity rail

New desktop invitations default to Full access; expand Restrict access for individual scopes. Existing grants keep their scope, so pair again to add `approve_tools`. The permission allows once-only decisions on pending requests, not automatic tool execution or policy editing.

Both native clients use the same activity fixtures in `packages/mobile-contract/activity-fixtures.json`. They retain text/activity order, group consecutive reasoning and tools into expandable rails, replace replayed arguments, and clear the entire transient state on stream reset. Pending approvals use the desktop queue and show tool arguments with allow/reject actions. All requests in a batch must be decided before the native run resumes; ACP uses its existing live broker. Foreground polling reflects decisions made on desktop.


### Navigation and composer

Chats live in a searchable sidebar grouped by desktop Project, with collapsible
sections and a new-conversation action per accessible, active project. New conversation
opens an unsaved composer; only its first non-empty send creates a stored chat.
The chosen project and model carry into that first message. If sending fails after
creation, retries reuse the created chat and retain the draft. Settings
is pinned to the sidebar and contains Desktop access and foreground Node controls.
iOS keeps the sidebar visible at tablet widths; phones use a drawer. The iOS
drawer stays in an opaque composited layer during its slide-out animation. Foreground
navigation refreshes automatically every ten seconds without a refresh button.

The composer is a compact single row while the keyboard is hidden. With the
keyboard visible it grows up to six lines and shows the model selector; Return
inserts a newline. A dedicated header action opens New conversation. Sending an
accepted message clears its draft and dismisses the keyboard. Failed or uncertain
sends retain the draft and are never retried automatically. Switching conversations
preserves drafts for the current app session. Native conversations offer the
backend-enabled model list, submitted with the next message; ACP conversations
keep their desktop model configuration.

Saved credentials reconnect automatically on launch and foreground return. A
temporarily unavailable desktop shows a retry screen instead of QR onboarding;
revoked credentials require pairing again. User messages align right and size to
their content, with smaller chat typography on both platforms.

Update the backend alongside the apps: navigation requires `/mobile/client/projects`
and project/model metadata on mobile chat responses. Project listings and creation
respect the device's existing chat scope; model selection forwards only an enabled
model, never arbitrary configuration or permission overrides.


Mobile chat and controls use shared `typeChat`, `typeControl`, `typeSection`,
`controlHeight` and `sidebarWidth` tokens. Both platforms use a centered wordmark
between equal-size navigation icons, outlined search fields, left-aligned
monospace project headings and a leading selection bar. Primary buttons retain
the desktop blue, square border and hard shadow. Native keyboard, selection,
model menus and system permission controls retain their platform behavior.


Successful connection opens the same unsaved start page as New conversation,
with the sidebar closed. The welcome area follows the desktop: a cube mascot,
the same localized time-of-day greeting, and a project selector. Changing the
project only updates the unsaved composer; there are no prompt starter cards. The first send remains
the only action that creates a stored conversation.

The native greeting cube adds a six-second float and perspective sway, with
two counter-rotating wireframes on a 24-second cycle. iOS pauses its 30 Hz
timeline in the background and honors Reduce Motion; Android uses Compose
animation layers and disables animation when system animators are disabled.

Model selection opens a separate selection panel owned by the conversation screen,
not by the keyboard-dependent composer row. Opening it clears input focus;
closing or selecting a model does not reopen the keyboard. This avoids popup
focus changes repeatedly removing and recreating the model menu.

Model and project choices share native Suzent selection panels: black title bars,
square outlines, hard shadows, yellow selected rows and explicit checkmarks.
Long lists scroll, and dismissal leaves the current selection unchanged.

### Pairing the same phone again

Use **Settings → Pair again**, without first forgetting the connection. With an
updated backend, the phone proves possession of its saved credential. An unchanged
scope and address reuse the token; changed permissions or a LAN/Tailscale address
change rotate it while preserving the desktop device entry. The previous token is
retired after the replacement is saved securely. Failed or interrupted rotation
retains recovery credentials and can resume on reconnect.

Forgetting the connection or clearing app storage removes that proof. Those phones
pair as new installations; revoke stale entries explicitly from desktop. Existing
duplicates are not deleted based on device names.

## Mobile versions and CI builds

Mobile versions are independent of the desktop/backend product version. Edit
`packages/mobile-contract/version.json`, then run
`uv run python scripts/generate_mobile_version.py` to update Android's
`version.properties` and iOS's `Config/Version.xcconfig`. Both platforms share the
marketing version; the source build number is used for local builds. The desktop
`scripts/bump_version.py` deliberately does not include these files. Protocol
compatibility continues to use the pairing protocol and capabilities, not matching
product version strings.

The **Native mobile** workflow runs for relevant pull request updates, relevant
pushes to `main`, and manual **Run workflow** requests. It first checks generated
version settings, then assigns both platforms build number `1000 + github.run_number`.
This increases with each new workflow run; retries keep the same build number.
CI overrides generated settings only in its checkout, without committing them.
Keep local builds below 1001; reinstalling a lower-numbered local build over a CI
build may require an explicit development downgrade. Preserve this numbering
sequence when introducing a separate release workflow.

After Android builds and unit tests pass, download
`suzent-android-<version>-<build>-debug` from the workflow run's **Artifacts** section.
Unzip it to obtain `app-debug.apk`. Artifacts are retained for 30 days and include
PR builds as well as main/manual builds; prefer a successful main build for testing.
These APKs are debug-signed using the runner's temporary development key. They are
not stable upgrade packages: their signature can differ from local installations
and other CI runs. Uninstalling an existing installation to resolve a signature
conflict removes its local connection credentials and requires pairing again.
A fixed signing key is required before distributing upgradeable releases.

iOS CI builds the simulator target without signing and does not upload a device IPA.
This workflow does not publish GitHub Releases, Play Store builds, or TestFlight
builds. Mobile release signing and `mobile-v*` release triggers are separate future
work; desktop `v*` release triggers are unchanged.
