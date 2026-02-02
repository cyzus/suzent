---
name: browser-skill
description: Use a real browser to navigate the web, see pages visually, and interact with elements.
---

## Overview

The Browser Skill allows you to control a real, headless Chrome browser instance. This is useful for:
- Navigating to websites.
- "Seeing" the page structure via semantic snapshots.
- Interacting with elements (click, type, fill, scroll).
- Handling dynamic content (JS) that standard POST/GET requests miss.

## Workflow

1.  **Open**: `open <url>` to navigate.
2.  **Inspect**: `snapshot -i` to get a list of interactive elements with ID references (e.g., `@e1`).
3.  **Interact**: Use the ID references to interact.
    - `click @e1`
    - `fill @e1 "search query"`
    - `press @e1 Enter`

## Commands

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `open` | `<url>` | Navigate to a URL. |
| `back` | - | Go back in history. |
| `forward` | - | Go forward in history. |
| `reload` | - | Refresh the page. |
| `snapshot` | `['-i']` | Get a semantic list of interactive elements (`@e` refs). |
| `click` | `<ref>\|<selector>` | Click an element (e.g., `@e1`). |
| `dblclick` | `<ref>\|<selector>` | Double-click an element. |
| `fill` | `<ref>\|<selector> <text>` | Clear and fill an input field. |
| `type` | `<ref>\|<selector> <text>` | Type text naturally (useful for auto-complete). |
| `press` | `<ref>\|<selector> <key>` | Press a specific key (e.g., `Enter`, `ArrowDown`). |
| `hover` | `<ref>\|<selector>` | Hover over an element. |
| `scroll` | `[dx, dy]` | Scroll the viewport (default: down). |
| `click_coords` | `<x> <y>` | Click at specific coordinates. |

## Tips
- Always use `snapshot -i` before interacting to get fresh `@e` references.
- `@e` references are **ephemeral** and may change after navigation or dynamic updates.
- Use `fill` for standard forms, `type` for complex inputs reacting to keystrokes.
