# Mobile changelog

## [mobile-v0.10.0] - 2026-11-14

### Release notes
- Show the specific GitHub label added or removed in inbox events.
- Clarify event status wording and remove button-like styling from event labels.
- Make the mobile inbox more compact and load older events without replacing the list.
- Inbox events show the linked conversation title and project before you open it.
- Group related GitHub inbox events into expandable PR and issue threads.
- Find scheduled tasks inside Inbox, with simpler navigation and a clearer, unclipped message list.
- Mobile Inbox now uses the desktop's filters, shows each event's source and delivery status, and opens threads on their own page.
- Polish Inbox with consistent selection colors, clearer conversation cards, and quieter event details.
- Fix mobile inline code wrapping and show previews for uploaded images.
- Make inbox events easier to scan with compact cards, clear titles, repository context and readable action labels.
- Read your inbox on iOS and Android with shared unread status across your authorized devices.
- Unify the conversation and inbox section controls with consistent sizing, styling, and selection behavior.
- Messages from other chats, scheduled tasks and goal mode now show as one quiet line in mobile chats; repeats with no reply merge, and a reply notes what it answers.
- Display uploaded images outside user text bubbles and match desktop message colors in light and dark mode.
- Unify Regent conversation bubbles and make its status panel available on mobile.
- Show Regent’s cross-conversation work queue instead of a per-chat plan in the mobile status panel.
- Files the agent sends you now appear together under its reply, as artifact cards on desktop and a clearer file row on the phone.
- Unify inbox threads across desktop and mobile with backend-owned grouping for all event sources.

## [mobile-v0.9.0] - 2026-11-13

### Release notes
- Fix inline code in Android tables missing its yellow background in dark mode.
- Keep Android image save and share menus near the long-press position, including in the full-screen viewer.
- On the phone, tap an image the agent made to view it full screen and zoom, and touch and hold to save it to your photos or share it.
- On the phone, typing while the agent works now offers Redirect (interrupt and continue with your message) and Queue (send when the reply ends), matching desktop.
- Images, videos and speech the agent makes now show under its reply on the phone, with videos and audio playing inline.
- On the phone, conversations and collapsed projects show when something is running or has replies you have not seen, like on desktop; opening a conversation marks it read on both.
- The agent can now hand you finished files with Send File: they arrive in the chat app you wrote from (Telegram, Slack, Discord, Feishu), under the reply on the computer, and on your phone, where you can download and share them.

## [mobile-v0.8.2] - 2026-11-10

### Release notes
- Android: inline code shows as a readable yellow chip in dark mode again, instead of a dark box with faint text or a whole line painted yellow.
- Allow connection status text to wrap and grow with the font size instead of clipping it.

## [mobile-v0.8.1] - 2026-11-09

### Release notes
- Citations inside bold or italic text, and citations written as plain [t0_src_1] labels, now render as source chips, and those paragraphs keep their formatting.
- Mobile sessions connected through a relay now look for a direct route in the background and switch when idle without reloading the chat.
- Mobile reconnects race available addresses and relay, with smoother connection progress.
- With reduced motion turned on, the thinking animation now shows finished robots stepping along the line instead of a frozen frame.
- Improve tool permission details and separate shell approval requirements from risk for read-only chained commands.

## [mobile-v0.8.0] - 2026-11-09

### Release notes
- Keep a collapsed activity rail closed while a reply is streaming, and stop streaming blue and a single failure from recoloring the whole rail.
- Long-press menus open beside the finger and stay inside the screen, including in the Android app.
- Reduce Android conversation entry flicker by preserving open messages, avoiding temporary empty greetings, and positioning history before layout.
- Smooth Android composer transitions and keep the voice or send button anchored while the input expands and collapses.
- Refine Android long-press menus with lighter styling, touch-aware placement, and smooth opening and closing animations.
- Reduce flashing during Android history loading with a delayed loading indicator and a subtle message fade-in.
- Use a deeper yellow in dark mode, and give inline code the same black border on phones as on desktop.
- Keep iOS composer actions anchored during expansion and collapse, and reduce conversation loading flashes with preserved messages and delayed loading feedback.
- See a conversation's plan and context usage from the phone, and choose appearance, text size, haptics and language in the mobile app's settings.
- Tables, cards, buttons and forms the agent shows now appear in the mobile chat, and you can answer them from your phone.
- iOS and Android now use a thicker layered gray assembly scan matching desktop.
- While pairing, the phone no longer shows a code to check; it waits for you to click Allow on your computer.
- Show live connection stages and a dual-node magnetic stream indicator while reconnecting to a desktop.
- Regent's chat on the phone no longer repeats the logo and name already shown in the header.

## [mobile-v0.7.2] - 2026-11-07

### Release notes
- Fix "Message too long" errors on iPhone when opening long chats or images, especially through the relay.

## [mobile-v0.7.1] - 2026-11-06

### Release notes
- Fix the iOS build so the relay connection ships in the App Store release.

## [mobile-v0.7.0] - 2026-11-06

### Release notes
- Android: when your computer isn't reachable directly, the app connects through your own Suzent relay, end-to-end encrypted.
- iPhone: reach your desktop through your own Suzent relay when no direct address answers, end-to-end encrypted.
- Keep voice and send buttons vivid blue with white icons in both light and dark mode.
- The mobile home screen switches between recent conversations and projects instead of stacking both, moves search and New conversation to header icons, uses monochrome tab icons, adds haptics and a clear unpin look to chat swipes, shows the connected desktop with a computer icon, shows a reply's model as quiet text instead of a box, opens Regent's reply actions with a long press on its bubbles, and lets the iPad sidebar be hidden with scheduled tasks as its own list.
- Share the desktop voice cube animation with iOS and Android and replace inactive composer buttons with voice, hang-up, and progress actions.
- Fix the voice cube animation appearing blank on Android devices.
- Start realtime voice conversations from the empty iOS and Android chat composer, with live captions and a hang-up control.
- Keep one call control during voice conversations and avoid stale Android connections when starting actions.

## [mobile-v0.6.2] - 2026-11-05

<!-- highlights -->
### Highlights

- **Switch computers when one is offline.** If your default desktop can't be reached, the reconnect screen now lists your other paired computers. Tap one to switch, even mid-attempt, or pair a new one from the same screen.
<!-- /highlights -->

### Release notes
- When the default desktop can't be reached, the reconnect screen now lists your other paired desktops so you can switch with one tap, even mid-attempt, or pair a new one.

## [mobile-v0.6.1] - 2026-11-03

### Release notes
- Optimize Android release size and improve edge-to-edge and large-screen compatibility.

## [mobile-v0.6.0] - 2026-11-02

### Release notes
- Pair the mobile app with several computers and switch between them from Settings, with a new Chats, Tasks and Settings bar on phones.
- The phone pairing QR code is much less dense and easier to scan, forgetting a connection on the phone revokes it on the computer, and pairing the same phone again replaces its old entry instead of adding another.
- On phones, searching chats opens its own page with the keyboard ready, and going back from a result returns to the results; on Android, loading chats no longer fails with "Backend request failed" after the app has been idle for a moment.

## [mobile-v0.5.4] - 2026-11-01

### Release notes
- Android pairing scans the QR code with the built-in scanner, so it works the same with or without Google Play services and sends nothing to Google.
- Tool approval buttons now sit side by side and the whole approval card stays above the composer on Android, and new conversations show the default project's translated name.

## [mobile-v0.5.3] - 2026-10-31

### Release notes
- The offline demo reads like real use: one clear demo banner instead of disclaimers in every reply.

## [mobile-v0.5.2] - 2026-10-31

### Release notes
- The Android chat list shows its settings button again; the wordmark had pushed it out of view.
- On iPad the conversation keeps a readable width, and starting the offline demo no longer flashes the pairing screen.
- Settings and the connection screen now link to the mobile privacy policy.

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
