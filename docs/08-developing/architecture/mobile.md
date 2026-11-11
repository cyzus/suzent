---
sidebar_position: 10
---

# Native mobile clients

## Architecture decision

Suzent mobile uses SwiftUI on iOS and Kotlin/Jetpack Compose on Android. Both
applications live in this monorepo; Python remains managed by uv, Android by
Gradle, and iOS by Xcode/Swift Package Manager. Existing desktop paths stay intact.
The clients share a wire contract and fixtures, not a cross-platform UI runtime.

The desktop backend owns agent execution, memory and chat history. Mobile has two
independent roles: a remote client and an opt-in foreground device Node. A Node
grant does not authorize HTTP access. No Python runtime runs on the phone.

## Status

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
connections must pair again. See the [pairing contract](../../../packages/mobile-contract/pairing.md).

Planned work is tracked in the [Roadmap](../roadmap.md#mobile-apps).

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

Enable desktop **Settings → Mesh → Network access**, restart, and use its LAN/Tailscale
address on port 25314 (never the phone's localhost) in the desktop pairing card.
The QR includes the preferred origin plus discovered LAN/Tailscale candidates.
Updated phones check candidate capabilities without credentials, then display the
first reachable compatible address for confirmation. A three-second timeout per
candidate bounds this check. Old single-origin invitations remain supported.
Select permissions on desktop, then pair and confirm on the phone. Saved connections retain
the confirmed address and the invitation's alternative addresses.
On both platforms, reconnect probes saved addresses without credentials with a
three-second timeout per address, including legacy HTTP connections in debug builds.
The entire reconnect has a twenty-second deadline and a Cancel action. Cancellation
also stops pending network requests; moving to the background cancels reconnect.
An unreachable desktop leaves the saved connection intact so the user can retry or pair again.
HTTPS/WSS is required for release builds. Debug builds
allow explicit HTTP addresses for a trusted LAN/tailnet; HTTP is not encrypted.
No certificate-validation bypass or automatic URL redirect is supported.

### Several desktops

A phone can hold credentials for several desktops but is connected to one at a
time. Both platforms store one encrypted record of saved desktops
(`{activeId, desktops: [{id, name, connection}]}`): a single Keychain item
(`account "desktops"`) on iOS, the existing Keystore-encrypted preference on
Android. A record from a single-connection build is read as one active desktop
and rewritten; on iOS the old `"primary"` item is then deleted. The id is a
local UUID. The name comes from the pairing preview and is refreshed from the
optional `desktop_name` in `/mobile/client/session`, falling back to the origin
host.

Pairing re-pairs the active desktop for **Pair again**. Otherwise it looks for a
saved desktop that matches the invitation: the same device-CA fingerprint when
both have one, else any shared normalized origin. Only that desktop's token
feeds the repair proof, rotation and reuse checks. A match replaces the entry;
no match adds one. Switching probes and loads the target with the usual
three-second-per-address and twenty-second limits before it resets any session
state, so an unreachable desktop leaves the open session untouched. A 401 forgets
only the desktop that returned it. Node tokens and remembered model choices stay
per connection. The pure list logic lives in `Desktops.kt` and
`SuzentCore/SavedDesktops.swift`, with unit tests on both platforms.

Phones show a bottom bar with Chats, Tasks and Settings. It's hidden while a
conversation is open. The desktop card at the top of Settings opens the Desktops
page (switch, swipe to forget, pair another). Tablets keep the split view with
the settings button in the sidebar. The Chats list shows one of Recent (pinned,
then the recent page) or Projects at a time, picked with a segmented switch under
the search field; iOS keeps the choice in `@AppStorage("homeListMode")`, Android in
saved state. On iPad the switch adds Tasks, which replaces the scheduled section,
and the sidebar can be hidden from its header and shown again from the detail
toolbar. Android tablets keep the scheduled section below the list.

On phones a header search icon (beside the New conversation icon) opens a separate search page
(iOS: a `Route.search` pushed under the conversation; Android: a `searching`
flag that replaces the tab home). Its query survives opening a result, so back
from that chat returns to the results; Cancel or back from the page clears it.
Tablets keep the inline sidebar field.

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
Debug builds install as Suzent Dev (`com.suzent.mobile.dev`, version name `-dev`), beside a
Play Store copy they could not replace because they are signed with the local debug key; the dev
app keeps its own pairing.
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
While a turn runs, the composer offers redirect and queue in place of Stop once
there is typed content, matching desktop's Enter and Cmd/Ctrl+Enter.
`POST /mobile/client/steer` (session capability `steer: 1`, requires both `send`
and `stop`) forwards text and an optional model to `/chat/steer-send`, or to
`/chat/send` when the turn already ended. On acceptance the client cancels its
current live stream, keeps the partial reply on screen (running or
approval-pending tools end as errors, as on desktop) and subscribes again. Queued
messages live only in the phone's memory, per conversation; the open
conversation releases the next one through the normal send path once it is
idle (not streaming, not running, no pending approvals). A failed release or
redirect returns its text and attachments to the composer instead of the queue,
so a failing desktop is not retried in a loop.
The native clients subscribe immediately after send acknowledgment, showing the
accepted user message locally while the backend remains authoritative. Live text
is published in 50 ms batches, with a final flush on completion or failure.
Network events accumulate away from the UI thread; only display batches reach the
native views. Android finishes each off-thread Markdown parse before rendering the
latest pending text, so frequent deltas cannot keep cancelling a long parse. Both
clients memoize saved transcript presentation. Live growth follows the bottom
without restarting a layout/scroll animation on every batch. Streamed prose uses
the same opaque Markdown renderer as saved messages, without per-fragment fades
or a synthetic cursor inserted into the document. Android skips rebinding a
native text view when its rendered content and styling are unchanged. Android tables retain the original Markwon table theme and row spans. A native
text view prepares table row measurements before visible layout, rather than
showing unmeasured rows and correcting their heights on the next frame. The scoped title index does not load transcripts/checkpoints;
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
   Forgetting the connection asks the desktop to revoke the device, then removes local credentials.

## Limits

The preview renders Markdown replies, PUA/ASCII citation markers, and structured
tool/reasoning activities in expandable activity rails. Citation and ordinary
web links open a native source-preview sheet with title, snippet, copy-link and
external-browser actions. Reading a source uses Safari View Controller on iOS
and Custom Tabs on Android. Inline citation capsules display source favicons
with a fixed-size fallback; repeated references have independent selection.
Multi-source citations list each resolved source in the sheet. Some legacy inline tool formats still require desktop; A2UI surfaces render natively (see [Inline surfaces](#inline-surfaces)). Shared palette and filtering
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
permission prompts stay native. iOS uses VisionKit QR recognition; Android uses embedded
ZXing, which needs no Google Play services and sends nothing off the device. Neither
scanner saves an image. Both apps provide English and Simplified Chinese strings.

Platform interactions stay native where the system already defines them. On iOS the
conversation list is the root of a `NavigationStack` (edge swipe back), and regular
width uses `NavigationSplitView`; Android animates list to detail under
`PredictiveBackHandler` and shows both panes from 840 dp. Conversation rows have a
context menu plus swipe actions (pin/unpin, delete with confirmation). Settings is a
native grouped list. Destructive confirmations use system alerts; rename and
edit-and-resend use sheets. Errors appear as a transient toast above the composer
(or at the bottom elsewhere), while pending approvals are pinned above the composer.
Only the latest message shows its action row; every message offers the same actions
(copy, share, edit, retry, branch, sources) from a long-press menu on its footer or
bubble, so message text keeps native selection. Send, copy, long press and approval
choices give haptic feedback, and iOS text follows Dynamic Type.

### Conversation info and phone preferences

`GET /mobile/client/chats/{id}/overview` (session capability `chat_overview: 1`) returns
the desktop sidebar's plan and context sections for one permitted chat: the chat's goal,
its tasks with status only (`blocked` is derived from `blocked_by`, as on the desktop),
and a context headline. The headline uses the stored `context_usage` (provider count,
else total tokens) against `resolve_context_limit` for the chat's model, plus the
breakdown's non-empty categories and reserve. Unlike the desktop chat load it never
deserializes agent state to estimate a missing count, so a chat with no usage reports
`usedTokens: null`. Clients skip the panel on older backends and in Regent's chat.

A header button opens the panel. iOS uses `.inspector`, which is a medium/large sheet
on compact width and a trailing column on regular width; Android uses a
`ModalBottomSheet` on phones and a `sidebarWidth` column beside the conversation from
840 dp. The panel polls every 4 s while the chat runs and every 15 s otherwise. The
offline demo returns a sample plan for its trip conversation from `demo.json`.

Settings → Preferences is local to the phone. iOS stores appearance, text size and
haptics in `@AppStorage` and applies them at the root with `preferredColorScheme` and
`dynamicTypeSize`; `suzentFeedback` gates every `sensoryFeedback`. Language opens the
app's page in iOS Settings. Android keeps them in the `app_preferences` file through
`AppPreferences`; `AppPreferencesProvider` overrides `LocalConfiguration.uiMode` (so
each `isSystemInDarkTheme` follows it) and scales `LocalDensity.fontScale`, and
`suzentHaptic` returns early when haptics are off. Language uses `LocaleManager`
per-app locales on Android 13+ with `res/xml/locales_config.xml`.

### Inline surfaces

Agent-rendered A2UI surfaces (`render_ui`, `ask_question`) arrive in saved messages as
`{"type": "a2ui", "surface": …}` parts and live as `CUSTOM` `a2ui.render` events on the
same `/mobile/client/live` stream; `a2ui.resolved` removes an answered deferred question.
Both clients decode the component tree (`A2UI.swift`, `A2UI.kt`) leniently: an unknown or
malformed component becomes `unknown` and renders nothing, so a newer desktop never breaks
a transcript. A surface is its own chunk in the reply, counts as part of the final reply
rather than the folded activity, and a later render of the same id replaces the earlier
one in the live buffer. Every desktop component has a native view: text (markdown through
the chat renderer), badge, button, table (scrolls sideways), form (text, number, select
with optional free text, multiselect chips, checkbox, textarea; required fields gate
submit), list, progress, divider, card, stack and columns (side by side only when each
column gets at least 140 pt/dp, otherwise stacked). HTML runs in a `WKWebView` with a
non-persistent data store or a `WebView` without file, content or DOM storage access,
gets a phone viewport and standards mode when it has none, opens followed links in the
browser, and bridges `postMessage({type: 'a2ui:action'})` back as an action. It always
sizes to its content with the desktop's auto-size shim (body height, re-measured on
resize, DOM changes, image loads and fonts, capped at 5000 pt/dp); an agent-given
`height` is only the first guess, because scrolling inside the page would fight the
chat's own scroll. Surfaces with `target: "canvas"`
also render inline until the conversation panel shows them.

Actions follow the desktop dispatcher. An ordinary button or form is sent through
`/mobile/client/send` as the desktop's `[canvas: action] "label" {context}` message
(sorted keys, with `surface_id` added); `submit_question` forms send the
"question: answer" text; a deferred `ask_question` posts to
`POST /mobile/client/surface-answer` (session capability `surfaces: 1`, `send`
permission, chat scope, answers up to 100 KB), which resolves the waiting tool call and
emits `a2ui.resolved`. Controls are enabled only with the send permission; ordinary
surfaces also need an idle conversation, deferred ones need the capability, and a
question form the user has since replied to stays disabled. User messages that came
from an action render as a "↳ label" line. Shared expectations live in
`packages/mobile-contract/surface-fixtures.json`; the offline demo's trip conversation
carries a sample surface.

### Mobile tool approvals and activity rail

New desktop invitations and desktop approvals default to the **Full control** preset, which grants every scope. The desktop picker offers presets that map onto `ClientPermissions` (`full`: every flag; `chat`: `all_chats`, `create_chats`, `send`, `stop`; `read`: `all_chats` only) plus **Custom** for individual flags and per-chat sharing. The presets exist only in the desktop UI; the wire format and stored grants are unchanged, and `ClientPermissions` still defaults every flag to false for API callers that omit them. Existing grants keep their scope. The permission allows once-only decisions on pending requests, not automatic tool execution or policy editing.

Both native clients use the same activity fixtures in `packages/mobile-contract/activity-fixtures.json`. They retain text/activity order, group consecutive reasoning and tools into expandable rails, replace replayed arguments, and clear the entire transient state on stream reset. Pending approvals use the desktop queue and show tool arguments with allow/reject actions. All requests in a batch must be decided before the native run resumes; ACP uses its existing live broker. Foreground polling reflects decisions made on desktop.


### Navigation and composer

Mobile chat summaries and transcripts include optional `platform` and
`parentChatId` metadata. The parent ID is null when it is outside the device's
shared-chat scope. Android and iOS use the same sidebar fixtures to nest and fold
sub-agents in a single layer under the topmost visible parent, retain unshared-parent
conversations as standalone rows, and include the root when searching for a child.
Descendants share one fold control on the main conversation row; child rows never
introduce another folding level. Scheduled conversations and their sub-agents
appear in a separate scheduled-tasks section.

`GET /mobile/client/session` advertises `scheduled_tasks: 1` when
`GET /mobile/client/scheduled-tasks` is available. Clients skip that request on
older backends. Heartbeat rows (`source="heartbeat"`) are excluded, as on the
desktop, and only tasks whose target conversation is permitted for the device are
included, covering bound tasks and isolated `cron-{id}` tasks. Unlike the desktop,
tasks bound to the focal agent's chat stay listed: the desktop hides them because its
Regent card shows them, and a paired device has no such card.
It exposes name, active/running/error flags, offset-qualified run times, an
openable chat ID only when that chat exists, and `chatUpdatedAt` plus
`lastRunFinishedAt` (the newest run's finish time) so a client can tell an unresolved
failure from one already answered in the chat; prompts and raw errors stay private.
A failure counts as resolved once the chat was updated after that run finished: it
leaves the failing rank, drops the failure status line, and shows the chat's activity
time instead of the run time, exactly as the desktop automation list does.
Both clients order the section like the desktop: unresolved failures first, then
active tasks, then paused ones, each group by next run (tasks without a next run
last). Rows show the desktop status line (paused, paused · failed, last run failed,
next run, active) with a running marker and the last-run date, and the section shows
the task count badge with a five-row preview followed by View all. Search bypasses
the preview so every match stays reachable. This sidebar is read-only. Pending tasks
remain visible without creating a chat. Heartbeat sessions and Regent's own card stay
desktop-only.

Chats live in a searchable sidebar grouped by desktop Project, with one project
expanded at a time — opening another collapses the previous one, matching the
desktop `filterId` model. Projects are ordered by recent activity, derived from the
newest chat each one owns because the chat listing already arrives newest first.
Sections run scheduled tasks, pinned chats, projects, then ungrouped conversations,
so the scheduled block sits above pinned chats as it does on the desktop. A New
conversation row sits under the header rule, mirroring the desktop sidebar body, and
projects have no create button of their own. New conversation opens an unsaved
composer; only its first non-empty send creates a stored chat.
The chosen project and model carry into that first message; an unsent composer shows
the seeded default project by the name the backend gives it (`Home`, from
`ChatDatabase.DEFAULT_PROJECT_NAME`) rather than a localised label. If sending fails after
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
keep their desktop model configuration. Both mobile apps remember the last explicit
model selection locally for each server address, including across app restarts.
New conversations restore that selection if the model is still enabled; existing
conversations retain their own configuration. Pending model choices are stored per
conversation and restored when switching chats, even before sending a message.
Once a fetched conversation confirms the choice, its server configuration takes
precedence again. Choosing Conversation default clears the remembered selection.
This preference is independent of the desktop preference. The backend reads each
conversation's saved model (including the original subagent model when no explicit
conversation model exists) for both display and sending. Accepted mobile sends
persist the model without replacing other conversation settings.

Completed messages have native footers with copy and timestamps. Assistant footers
also show the recorded per-message model (falling back to the conversation model
for older messages), a sources drawer, and conversation branching when creation
is permitted. The latest user message can be edited and resent, and the latest
turn retried, with both send and conversation-management permission. These actions
require an idle conversation, ask for confirmation, and use the desktop retry
checkpoint behavior through the scoped `/mobile/client/message-action` endpoint.
Replay is unavailable after an intervening automation turn or when the latest
user message no longer matches the saved checkpoint. Branches include the full
assistant/tool continuation associated with the selected reply, even when its
tool rows are hidden by the mobile presentation.
Replay also requires the checkpoint's recorded completion revision to match the
current conversation revision, so transcript-hidden background turns invalidate
it. Older checkpoints without that marker require a new user turn before mobile
replay becomes available.

Saved credentials reconnect automatically on launch and foreground return. A
temporarily unavailable desktop shows a retry screen instead of QR onboarding;
revoked credentials require pairing again. User messages align right and size to
their content, with smaller chat typography on both platforms.

Update the backend alongside the apps: navigation requires `/mobile/client/projects`
and project/model metadata on mobile chat responses. Project listings and creation
respect the device's existing chat scope; model selection forwards only an enabled
model, never arbitrary configuration or permission overrides.


Mobile chat and controls use shared `typeChat`, `typeControl`, `typeSection`,
`typeSidebarSection`, `controlHeight` and `sidebarWidth` tokens, plus the chrome
tokens `borderWidth`/`borderWidthHeavy`, `shadowOffset`/`shadowOffsetHeavy`,
`shadowOffsetOverlay`, `radius` and `selection-light`/`selection-dark`.
`spaceRow` (10) is the vertical rhythm of every sidebar row — chat, scheduled
task, and heading spacing all read from it, so the list keeps one cadence.
`borderWidthHeavy` draws the rules in the sidebar chrome, `shadowOffsetOverlay`
sits under menus, dialogs and the selector panels, and `shadowOffsetHeavy` covers
the assistant badge and the model/project selection panels. No shadow offset is
hardcoded in either client. Both
platforms use a centered wordmark between equal-size navigation icons and
outlined search fields. The sidebar follows the desktop treatment: a 3 px rule
under its header and along the drawer edge, 10 pt uppercase tracked section
headings, hairline rules between rows, and a grey fill for the current
conversation instead of a leading selection bar. Header icons, the sidebar's New
conversation row and project headers are plain rows from the shared icon/row
primitives — square, no border or shadow, quiet 8% pressed fill — instead of
Material `IconButton`, a bare SF Symbol or a bordered card; the desktop sidebar
is equally flat, so per-row borders and shadows would read heavier than the
baseline. Popup menus drop their platform elevation in favour of the shared hard
shadow, and dialogs use a 2 px rule with a ruled uppercase header. Primary
buttons retain the desktop blue, square border and hard shadow. Native keyboard,
selection, model menus and system permission controls retain their platform
behavior; iOS rename and delete confirmations still use system alerts.


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

Forgetting the connection revokes the device on the desktop when it is reachable,
then removes that proof. Phones also send a random per-installation ID on claim;
the desktop stores only its hash. A new grant for a known installation keeps the
old device ID and stays provisional until the phone confirms it, which retires the
stale grant. The ID survives forgetting the connection (Android app storage; iOS
keychain, this device only), but not clearing Android app data. Device names are
never used to match phones.

## Mobile versions and CI builds

Mobile versions are independent of the desktop/backend product version. Add a
`mobile` impact declaration under `.releases/changes/` in feature PRs. The
`release/mobile` plan updates `packages/mobile-contract/version.json` and generates
Android's `version.properties` and iOS's `Config/Version.xcconfig`; do not bump these
files manually in feature PRs. See [the release guide](../contributing/releasing.md). Both platforms share the
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
sequence for debug previews. Signed releases use their own stable range described
in [Mobile release distribution](../contributing/mobile-releases.md).

After Android builds and unit tests pass, download
`suzent-android-<version>-<build>-debug` from the workflow run's **Artifacts** section.
Unzip it to obtain `app-debug.apk`. Artifacts are retained for 30 days and include
PR builds as well as main/manual builds; prefer a successful main build for testing.
These APKs are debug-signed using the runner's temporary development key. They are
not stable upgrade packages: their signature can differ from local installations
and other CI runs. Uninstalling an existing installation to resolve a signature
conflict removes its local connection credentials and requires pairing again.
A fixed signing key is required before distributing upgradeable releases.

iOS PR CI builds the simulator target without signing. The separate **Release
mobile** workflow builds signed Android APK/AAB files and uploads an iOS device
archive to App Store Connect after a `release/mobile` merge. It requires the
`mobile-release` environment and signing credentials; see
[Mobile release distribution](../contributing/mobile-releases.md) for setup, outputs, build-number
ranges, retry behavior, and acceptance gates. Rolling `mobile-preview` releases
and automatic Play Store submission remain future work.

## Conversation management

Long-press a conversation on iOS or Android to pin/unpin, rename, move it to a
shared project, or delete it after confirmation. Pins and metadata are stored on
the backend and shared with desktop. The mobile rows use the same yellow pressed
feedback, 44-point minimum menu targets, outlined surfaces, and destructive red
actions on both platforms.

These actions require the independent `manage_chats` permission. The **Full
control** preset includes it; **Chat only** and **Read only** do not. Existing
grants keep whatever they had; change it in desktop Settings → Mobile access.
Sending messages and creating chats do not grant management access. Old backend
sessions without this field are treated as not authorized by both native clients.
Moving/deleting a running conversation is rejected; project moves may not affect
descendants outside the device's shared scope. Mobile deletion never cascades to
subagent conversations. Existing credentials remain valid across this upgrade.

## Encrypted local pairing

For a local HTTP backend address, **Pair phone** now creates a separate local
HTTPS endpoint automatically. Scan the QR in the native app and confirm the
connection. No Tailscale account, domain, or system root-certificate installation
is required. If the desktop address field already contains a public HTTPS origin,
that address keeps normal system certificate validation instead.

Allow the desktop backend through the local firewall when prompted. The encrypted
mobile listener uses a persisted port distinct from the desktop HTTP port and
runs only after local pairing has been enabled. Keep `mobile_tls` in the user
configuration directory across upgrades; it contains the private device identity.
Its server certificate renews without requiring new pairing. Saved addresses are
retried on reconnect; `.local` name resolution can help after an IP change but is
network-dependent. Rescan if none of the saved addresses resolve to the desktop.

A new device identity is never accepted during reconnect. If the desktop's keys
were intentionally replaced, scan a fresh QR to authorize it again. Public HTTPS,
Tailscale and reverse proxies remain supported as optional connection methods;
this local listener does not provide internet traversal or a relay service.

### Updating paired-phone permissions

The desktop operator can replace a device's complete permission set with
`POST /mobile/devices/{device_id}/permissions` and a `permissions` object matching
`ClientPermissions`. The route uses the host authorization boundary; a mobile
credential cannot change its own permissions. Invalid payloads return 400 and
unknown devices return 404.

The store persists the replacement atomically before updating in-memory grants.
The existing credential remains valid, and subsequent mobile requests check the
updated scope. The legacy `/management` route remains available for older
clients and changes only `manage_chats`.

The desktop editor keeps a local draft until Save. Cancel discards the draft;
failed saves leave it available to retry.

## Offline demonstration

Both native apps expose **Try offline demo** as a quiet text button at the bottom
of the unpaired connection screen. Once paired, the entry is under **Settings →
About**; it is absent from connection help and the regular chat surface. It is
available in release builds to everyone. The pinned welcome conversation identifies
scripted responses; Settings provides **Reset demo**
and **Exit demo**. Existing desktop pairing credentials are retained when entering or leaving
the demo, and demo operations never use them.

The regular conversation UI consumes a `MobileClient` interface. `SuzentClient`
(iOS) and `BackendClient` (Android) implement the real transport; `DemoClient`
implements a local workspace with no network transport. Both platforms bundle the
same English/Chinese fixtures from
`packages/SuzentCore/Sources/SuzentCore/Resources/demo.json`. Android includes that
directory as an asset source; SwiftPM processes it as a package resource.

The native navigation shows Regent and New conversation as separate entries, then
pinned chats, a three-conversation recent preview with View all, and expandable
projects. Scheduled tasks are collapsed below the projects; searching reveals
matching task rows. Settings is available from the top toolbar.

The bundled English/Chinese demo includes a successful UI review with tool
activity, a simulated source timeout, a daily note, a trip plan, an approval
example, a welcome chat and Regent. Existing demo workspaces are preserved on
upgrade; Reset demo loads the latest examples.

The demo supports scripted streaming, stop, tool approval/rejection, project/model
selection, new conversations, pin/rename/move/delete, branching, editing and retry.
Trip and tool-approval prompts are offered on the start page; arbitrary input gets
a clearly labelled example response. Attachment selection uses the real native
pickers, but the local client records only names and MIME types. It neither reads
attachment bytes nor uploads or analyses them. No model API key is needed.

Conversation changes are persisted in a separate versioned demo JSON file in app
storage. Running turns progress independently of a stream observer while the app
is alive, and reconcile on foreground return. An unfinished turn from a terminated
process is marked interrupted on reopening. Reset restores the bundled examples.
Pairing and foreground Node controls remain real-desktop features and are explained
in demo Settings. Example citations have no remotely fetched favicons; opening a
source website is an explicit user action requiring internet access.

For review, provide the exact demo entry and scenario steps, disclose all simulated
behaviour, and include a physical-device video of real desktop pairing and
interaction. This mode provides an accessible demonstration, not a guarantee that
stores will waive access to the real connection flow.

### Regent

The chat index prepends a `platform: "focal"` summary for `all_chats` grants.
Discovery does not create the singleton or start its heartbeat; the existing
chat-detail path initializes it when opened. The optional `regent` object carries
`waiting`, `unread` and `lastMessageAt`. Ordinary clients can ignore it. Detail
responses omit the hidden system project's navigation metadata.

`ClientPermissions.permits_chat` requires `all_chats` for `focal-suzent`, including
when its ID appears in an explicit chat list. The same guard covers sending,
observing, stopping and approvals. Mobile management, retry/edit/fork and
attachment sends reject Regent. `POST /mobile/client/chats/{chat_id}/read` resets
the shared unread counter after an authorized read. Discovery itself never marks
messages read.

Both native clients render Regent as a fixed navigation entry and reuse the
normal conversation, stream and recovery mechanisms. A collapsible list links to
the five most recent authorized direct child conversations. Navigation polling updates
status; a background Regent turn discovered in the selected conversation attaches
to the existing observer. Read receipts from polling only run while its conversation
is visible. The crown/eyes animate while working, the gem pulses when waiting,
and new message timestamps trigger a nod. System reduced-motion settings and
foreground lifecycle gate animations.

`RegentPresentation` in Swift and Kotlin transforms normalized tool results into
separate visible bubbles and user reactions. It suppresses quiet heartbeat replies
and in-flight delivery calls while retaining failed/malformed calls for inspection.
The raw history and live buffers remain authoritative. Reactions stop at background
trigger boundaries. Cross-platform delivery cases live in
`packages/mobile-contract/regent-fixtures.json`.

### Native activity presentation

Swift and Kotlin `ActivityPresentation` consume persisted run timings, deduplicate
run IDs and sum resumed active durations without including approval waits. Shared
cases live in `packages/mobile-contract/activity-timing-fixtures.json`. Missing
timing displays Activity instead of a fabricated duration.

`ActivityTurn` folds completed process content beneath Worked for while preserving
final prose and Regent delivery bubbles. Pending approvals remain visible. Nested
activity rails and tool blocks expose status, formatted input/output, copy actions
and bounded detail scrolling. Tool-category animations and disclosure transitions
respect reduced motion; ongoing icon animations pause in the background. These
are native generic tool renderers, not the complete desktop rich-renderer set.

Starting a new conversation detaches the selected local stream observer only after
composer loading succeeds. Generation guards reject stale updates, and no backend
stop is sent. Regent and ordinary tasks therefore continue independently.

### Paged conversation navigation

The first screen loads 30 recent chats and a separate pinned page. Projects carry
server counts and fetch their own first page when expanded; Load more requests
another 30. Title search runs on the server across the authorized history, so an
older conversation remains discoverable even if it was never loaded on the phone.

The clients use `chat_pagination: 1` and the navigation/page/status routes documented
in `packages/mobile-contract/README.md`. Older servers retain the legacy index
fallback. Foreground polling refreshes loaded summaries in batches of at most 100;
metadata and the short recent page refresh once per minute. Page loads and search
results are guarded against navigation changes and cancellation. Pull to refresh
on iOS or the refresh action on Android restarts from the newest page. Regent,
project counts and pin discovery do not depend on the recent page.

The demo implements the same paging contract locally. Paging, old-title search,
independent pins, duplicate merges and access-scoped counts have regression tests.

### Voice composer and shared animation

The paired-device `/mobile/client/voice` WebSocket reuses `VoiceBridge` and checks
conversation access plus send/stop permissions. Native audio capture and playback
remain in each app's `VoiceSession`; the server's state and working events and the
microphone level drive the animation.

Desktop and mobile use `frontend/src/lib/voice/voiceCubeRenderer.ts` and
`voiceCubeSim.ts`. Run `npm run build:mobile-voice` in `frontend/` after changing
these files. This bundles an offline HTML asset in SuzentCore's resources, which
both apps already package. `npm run check:mobile-voice` and the frontend test
check that this asset matches the shared source. The mobile views host only the
animation in a transparent WebView. The canvas uses explicit positioning because
a flex-positioned canvas could render pixels without appearing on screen in
Android WebView. The WebView has no audio, remote assets, or native
JavaScript bridge; controls, captions, and permissions remain native. Dark mode
and reduced-motion preferences are passed to the shared renderer.

`ComposerAction` in each client prioritizes cancel/hang-up during a call, so task
stopping never appears alongside hang-up. Outside calls it shows stop for running
tasks, progress while busy, send for text/attachments, or voice for an empty
composer. Voice setup and permission errors
produce actionable messages instead of a disabled empty-composer button.

Android uses a separate non-pooling transport for mutations and voice handshakes
so they do not inherit idle sockets from background polling. Read requests keep
their own connection pool and safe retry policy.
