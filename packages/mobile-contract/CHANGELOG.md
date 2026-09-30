# Mobile changelog

## [mobile-v0.2.0] - 2026-09-30

### Release notes
- Add native conversation context menus, responsive pressed states, and explicit device-scoped conversation management permissions.
- Remember mobile model choices for new conversations and preserve pending choices when switching chats.
- Render PUA and ASCII citation markers and open their sources through native confirmation prompts on iOS and Android.
- Retry ambiguous mobile sends safely on iOS and Android by deduplicating stable client message IDs on the backend.
- Add the rectangular assembly-line thinking badge, lightweight streaming text fades, and smoother bottom following on iOS and Android.

## [mobile-v0.1.1] - 2026-09-27

### Release notes
- Bound desktop reconnection time on iOS and Android, allow cancellation, and make re-pairing available when a saved desktop is unreachable.
- Align iOS and Android controls, settings, reconnection, inputs, notices, and bottom-sheet selectors with the Suzent visual language.
- Restore local desktop pairing for release mobile apps with QR-scoped HTTPS trust and reliable credential rollback.
- Add signed Android release artifacts and iOS TestFlight upload automation for reviewed mobile releases.
