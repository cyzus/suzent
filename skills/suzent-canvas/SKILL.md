---
name: suzent-canvas
description: Render tables, forms, cards, buttons, dashboards, or custom interactive visuals in Suzent's desktop canvas or inline chat UI. Use when structured interactive presentation materially improves a desktop conversation; do not use for social or headless delivery.
---

# Canvas

Use `render_ui` only when the current environment can display A2UI surfaces. Prefer a
normal text response for simple answers, one-off confirmations, social channels, and
headless automation.

## Workflow

1. Choose a stable `surface_id` that describes the content.
2. Leave `target` as `inline` (the default); the user can pop a surface out to the side
   panel or fullscreen. Use `target="canvas"` only for a surface kept in view and
   updated while the conversation continues, such as live progress or a dashboard.
3. Build the smallest component tree that communicates the result, laid out for a
   narrow column (roughly 360-700px): stack rather than spread wide.
4. Reuse the same `surface_id` to update an existing surface.
5. Set an `action` on every button and form; use `context` for stable identifiers.

Use typed components for ordinary UI. Read `references/components.md` before building a
non-trivial tree, custom HTML visualization, or multi-step form.

## Constraints

- Use `content` for text and `label` for buttons or badges; never invent a `text` field.
- Keep action names stable and specific because they return to the conversation as
  `[canvas: <action>]` events.
- Do not render a choice UI merely because options exist. Use it when clicking is
  meaningfully easier or less error-prone than replying in text.
- Treat HTML as untrusted presentation code. Keep it self-contained, do not include
  secrets, and use `postMessage` only for minimal JSON action payloads.
- If `render_ui` reports that canvas is unavailable, continue with an equivalent text
  response rather than retrying the same call.
