# Shared presentation

`tokens.json` is the source for desktop and native colors, border/shadow dimensions,
ignored internal tool names, and legacy compaction summary markers. Desktop imports
it directly in Tailwind and the existing message renderer. Native code and the CSS
accent variable are generated with:

```sh
uv run python scripts/generate_presentation.py
uv run python scripts/generate_presentation.py --check
```

Generated files are checked in, so building either native app does not require
Python. Mobile CI rejects stale output. Do not edit generated files manually.

Compose and SwiftUI retain native views; React components are not executable in
these runtimes. Their presentation adapters prefer structured text, keep tools and
reasoning in expandable activities, deduplicate persisted tool results by call ID,
and apply the shared filtering policy. Both adapters run the same cases from
`packages/mobile-contract/presentation-fixtures.json`.

Markdown uses the desktop's existing renderer, Android Markwon, and SwiftUI
MarkdownUI (pinned 2.4.1). These are separate native rendering engines, not identical
layout implementations. MarkdownUI is in maintenance mode; its stable iOS 15+
compatibility allows retaining our iOS 17 minimum. See the
[MarkdownUI project](https://github.com/gonzalezreal/swift-markdown-ui) and
[Markwon table documentation](https://noties.io/Markwon/docs/v4/ext-tables/).

Currently shared: palette and filtering policy. Currently native-specific: message
layout, Markdown rendering, disclosure state. Not yet at desktop parity: attachments,
A2UI, citations, tool approvals, syntax highlighting, Mermaid, complete legacy
inline tool-tag parsing, or grouping entire agent turns into one activity rail.
Unsupported structured activities remain visible as a desktop-view placeholder.
