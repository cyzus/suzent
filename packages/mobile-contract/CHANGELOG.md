# Mobile changelog

## [mobile-v0.3.0] - 2026-10-10

### Release notes
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
