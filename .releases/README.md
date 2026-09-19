# Product release declarations

Add a uniquely named JSON file in `changes/` to a feature PR:

```json
{
  "products": {"desktop": "patch", "mobile": "minor", "browser": "patch"},
  "summary": "Describe the user-visible change."
}
```

Allowed impacts: `none`, `patch`, `minor`, `major`. `none` requires a `reason`.
Desktop includes the backend. Mobile includes both iOS and Android. Browser
includes the Chrome/Edge extension and keeps its own manifest version.
Merged declarations are immutable. Product ledgers in `state/` are generated on
release branches; reviewed version decisions live in `overrides/`.

See [the release guide](../docs/03-developing/releasing.md) for CI checks,
independent release PRs, migration, and persistent overrides.
