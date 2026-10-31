# Mobile changelog

## [mobile-v0.5.1] - 2026-10-31

### Release notes
- The iOS app now ships a privacy manifest, declares its encryption use, and no longer reuses a pairing left behind by a previous installation.

## [mobile-v0.5.0] - 2026-10-31

<!-- highlights -->
### Highlights

- **Regent in your pocket.** Regent comes to iOS and Android with its own access scope and new conversations of its own. It rests as the plain Suzent head and puts on its circlet when pressed, just like on the desktop. Pair with desktop 0.19.0 for the full experience.
- **Feels like a native app.** Native navigation, menus, swipe actions, sheets, sharing and haptics on both platforms. Conversations open on a full-screen home page with search, and approvals stay pinned above the composer.
- **The desktop's personality, on mobile.** The robot badge reacts to what the agent is doing, tools show their desktop icons and animations, and the activity rail sums up pages visited, tasks delegated and skills used.
- **Faster with long histories.** Conversation lists load page by page, search runs on the desktop over the chats you are allowed to see, and projects load on demand.
- **Easier pairing.** The pairing screen is simpler, the scan button sits within thumb reach, and you can paste an invitation from a sheet.
<!-- /highlights -->

### Release notes
- Bring the desktop chat animations to mobile: the robot badge with its personalities and reactions (startled by failures, skeptical while approval waits, a face per tool, dozing when idle), the desktop tool icons and their running animations, and the activity rail's summary categories such as pages visited, tasks delegated and skills used.
- Page native conversation lists, search authorized titles on the server, load projects on demand, and refresh loaded summaries without repeatedly downloading the entire index.
- Make mobile conversations a full-screen home page with search, new-chat actions, and back navigation.
- Use native navigation, menus, swipe actions, settings, sheets, sharing and haptics on iOS and Android, unify the mobile visual rules, pin approvals above the composer, and make activity disclosures expand and collapse smoothly.
- Simplify the mobile pairing screen before scanning: a centered welcome, the scan button within thumb reach, a one-line hint for where to find the QR code on desktop, and pasting an invitation in a sheet.
- Keep the project order on the mobile home screen steady when projects are expanded, and stop iOS from shuffling chat rows that appear in both Recent and an expanded project.
- Bring Regent to native mobile with scoped access, independent new conversations, expandable activity and tool details, a lighter home screen and richer offline examples.
- Match the desktop Regent row on mobile: it rests as the plain Suzent head and puts on its circlet with the desktop coronation while pressed.

## [mobile-v0.4.1] - 2026-10-26

### Release notes
- Fix iOS release archiving by applying the distribution provisioning profile only to the app, leaving the offline demo resource bundle unprovisioned.

## [mobile-v0.4.0] - 2026-10-26

### Release notes
- Keep the original Android table appearance while preparing Markwon row measurements before display to avoid repeated collapsed-height frames during streaming.
- Reduce iOS chat scrolling work by keeping scroll measurements out of SwiftUI rendering updates and avoiding repeated message-history scans.
- Refine the iOS sidebar with a compact search field, tighter project spacing, and lighter section headings and Settings styling.
- Restart approval monitoring after retrying or reopening the same conversation so new tool approvals remain actionable.
- Align the mobile composer with the desktop layout using a compact single-line input that reveals the attachment and model toolbar when editing, a matching attachment panel that moves the transcript and composer together when opened with the plus button, square send and stop controls, and desktop-style activity summaries, file counts, current-rail state, and timeline nodes.
- Align the empty-chat greeting cube on Android and iOS with the desktop: a true 3-D cube with a rotating sigil, soft shadow, and reactive logo eyes.
- Add a bilingual offline demo on iOS and Android with scripted streaming, tool approvals, local attachments, persistent sample conversations, and reset/exit controls without a backend or model API key.
- Align the iOS and Android sidebar with the desktop: shared border, shadow and spacing tokens, single-expand projects sorted by recent activity, scheduled tasks ordered like the automation list with heartbeat filtering and failure-handled suppression, full-height drawer rule, flat rows and an inline sub-agent control.
- Polish mobile sidebar and activity presentation, speed up pairing with parallel address discovery and clearer progress, fix Android dark-mode tables, and improve desktop pairing QR readability.
- Stabilize mobile streamed replies with background event batching, coalesced Markdown rendering, cached history presentation, and direct bottom following; remove fragment opacity fades and inline cursors that caused flashing and repeated reflow.

## [mobile-v0.3.0] - 2026-10-14

### Release notes
- Declare supported iOS screen orientations so App Store Connect accepts iPad-capable builds.
- Reduce iOS message footer copy, edit, retry, and branch icons to a consistent 13-point size while preserving their existing touch areas.
- Attach photos, videos, and files to messages from the iOS and Android apps, including taking a photo or video with the camera.
- Use charcoal surfaces, softer gray outlines, and near-black hard shadows in Android and iOS dark mode, with theme-aware code blocks and brighter links.
- Show the current conversation title in the mobile header, retain the Suzent wordmark for new conversations, and remove the duplicate title above messages.
- Use the Android system device name during pairing and refresh stored names when re-pairing with an existing credential.
- Use the canonical black-and-white Suzent logo with curious glances and blinking during mobile reconnection. Simplify the screen to one status line and move pairing actions into connection help, respecting reduced motion and app background state.
- Show nested sub-agent conversations and a separate scheduled-tasks section in both mobile sidebars, backed by scoped navigation metadata and scheduled-task reads.
- Render sub-agent and scheduled system reminders as compact disclosure rows on iOS and Android, hiding inbox delivery metadata and collapsing long bodies like desktop.

## [mobile-v0.2.0] - 2026-10-01

### Release notes
- Add native conversation context menus, responsive pressed states, and explicit device-scoped conversation management permissions.
- Add native message footers with metadata, copy, sources, and scoped replay and branching actions; correct mobile conversation model selection.
- Remember mobile model choices for new conversations and preserve pending choices when switching chats.
- Render PUA and ASCII citation markers and open their sources through native confirmation prompts on iOS and Android.
- Keep completed mobile assistant replies separate when later autonomous replies arrive.
- Retry ambiguous mobile sends safely on iOS and Android by deduplicating stable client message IDs on the backend.
- Add the rectangular assembly-line thinking badge, lightweight streaming text fades, and smoother bottom following on iOS and Android.
- Show one assistant badge and footer per mobile reply across activity steps and final text on Android and iOS.

## [mobile-v0.1.1] - 2026-09-27

### Release notes
- Bound desktop reconnection time on iOS and Android, allow cancellation, and make re-pairing available when a saved desktop is unreachable.
- Align iOS and Android controls, settings, reconnection, inputs, notices, and bottom-sheet selectors with the Suzent visual language.
- Restore local desktop pairing for release mobile apps with QR-scoped HTTPS trust and reliable credential rollback.
- Add signed Android release artifacts and iOS TestFlight upload automation for reviewed mobile releases.
