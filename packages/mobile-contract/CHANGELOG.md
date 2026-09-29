# Mobile changelog

## [mobile-v0.1.2] - 2026-09-29

### Release notes
- Retry ambiguous mobile sends safely on iOS and Android by deduplicating stable client message IDs on the backend.

## [mobile-v0.1.1] - 2026-09-27

### Release notes
- Bound desktop reconnection time on iOS and Android, allow cancellation, and make re-pairing available when a saved desktop is unreachable.
- Align iOS and Android controls, settings, reconnection, inputs, notices, and bottom-sheet selectors with the Suzent visual language.
- Restore local desktop pairing for release mobile apps with QR-scoped HTTPS trust and reliable credential rollback.
- Add signed Android release artifacts and iOS TestFlight upload automation for reviewed mobile releases.
