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

## Mobile component contract

Button color roles are semantic: neutral navigation, disclosure, selection, and
secondary actions use black in light mode and white in dark mode. Only primary
actions use blue; destructive actions use red. Camera-overlay controls remain
white for contrast. Android text actions use `SuzentTextButton`; iOS inherits
neutral tint. Input focus, links, and live status keep the blue accent.

SwiftUI and Compose implement the same primitives in their `PresentationViews`
files. Reuse these for new screens instead of default platform controls:

| Component | Contract |
| --- | --- |
| Action | 15 pt/sp semibold, minimum height 44, padding 12/16 horizontal and 8 vertical, 2 px border and bottom-right shadow; pressed face moves onto shadow; disabled opacity 45% |
| Quiet/destructive action | Same target and typography, without border or shadow; destructive text is red |
| Text input | 15 pt/sp, padding 12, minimum height 44, 2 px outline turning blue on focus; invitation accepts 3–6 lines |
| Toggle | Entire labeled row activates the switch; 44×26 rectangular track, 18×18 thumb, 150 ms transition, native accessibility state |
| Notice | Yellow background, black 13 pt/sp text, dismissal target at least 44 high |
| User message | Right aligned, intrinsic width up to 320, 40 minimum leading space, 12 padding, yellow fill, 2 border and hard shadow; no redundant author label |
| Selection trigger | Shared model/project control, 15 semibold, 44 minimum height, 12 horizontal padding, neutral text, optional muted prefix, truncating value, separate chevron |
| Selection panel | Bottom sheet, black header, white title, yellow selected row, minimum row height 48, 16 page gutter |
| Settings | 16 page gutter, 24 section spacing, outlined access and Node cards |
| Reconnection | Badge, section heading, primary reconnect, secondary pairing, quiet forget; same busy/cancel hierarchy |

The shared tokens define dimensions, type sizes, and colors; platform implementations
retain native keyboard, focus, and accessibility. iOS selectors use an in-page
modal overlay so system sheet chrome does not wrap the Suzent panel; dismiss via
the backdrop, close button, selection, or accessibility escape. Build both clients
when changing a primitive and inspect light/dark themes, large text, pressed/disabled
states, and long translated labels. Component parity does not imply pixel-identical
font metrics or Markdown layout.

Both clients support approvals and grouped activity rails. Remaining desktop parity
work includes attachments, A2UI, citations, syntax highlighting, Mermaid, and complete
legacy inline tool-tag parsing. Unsupported structured activities remain visible as
a desktop-view placeholder.
