---
name: canvas
description: Render rich interactive UI surfaces (tables, forms, cards, buttons) in the sidebar canvas or inline in chat using the render_ui tool.
---

# Canvas (A2UI) Skill

Use `render_ui` to display structured, interactive content alongside the chat. Surfaces appear in the sidebar canvas panel and persist across the session.

## Quick Reference

```
render_ui(surface_id, component, title="", target="canvas")
```

- **surface_id** — stable slug like `"results"` or `"booking_form"`; calling again with the same id *replaces* (upserts) the surface
- **component** — dict with a `"type"` field describing the root component
- **title** — label shown in the canvas tab strip (defaults to surface_id)
- **target** — `"canvas"` (sidebar, default) or `"inline"` (inside the chat message)

## Component Types

### Containers — have a `"children"` list

| Type | Description | Extra fields |
|------|-------------|--------------|
| `card` | Titled bordered panel | `title` |
| `stack` | Vertical (default) or horizontal group | `direction: "horizontal"` |
| `columns` | Side-by-side columns | `widths: [1, 2]` (relative ratios) |

### Leaves

| Type | Key fields | Notes |
|------|-----------|-------|
| `text` | `content`, `variant` | variants: `body` (default), `heading`, `subheading`, `caption`, `code` |
| `badge` | `label`, `color` | colors: `success`, `warning`, `error`, `info`, `default` |
| `button` | `label`, `action`, `variant`, `context` | variants: `primary`, `secondary`, `danger` |
| `table` | `columns [{key, label}]`, `rows [{}]` | |
| `form` | `action`, `submit_label`, `fields [{name,label,type}]` | field types: `text`, `number`, `textarea`, `select` |
| `list` | `items [str]`, `ordered` | items support markdown |
| `progress` | `value` (0-100), `label` | |
| `divider` | — | |

**Critical:** use `label` for buttons/badges, `content` for text. Never use `"text"` as a field name.

## Interactions

When the user clicks a button or submits a form, you receive a message:

```
[canvas: <action>] "<button_label>"       ← button click
[canvas: <action>] {"field": "value"}     ← form submit
```

Always set `"action"` on buttons and forms so you can identify what was triggered.
Use `"context"` on buttons to pass extra data: `{"context": {"id": 42}}`.

## Examples

### Card with status badges and actions
```python
render_ui(
    surface_id="status",
    title="Analysis",
    component={
        "type": "card",
        "title": "Results",
        "children": [
            {"type": "text", "content": "Evaluation complete."},
            {"type": "badge", "label": "92% Accuracy", "color": "success"},
            {"type": "button", "label": "Export CSV", "action": "export_csv"},
            {"type": "button", "label": "Re-run", "action": "rerun", "variant": "secondary"},
        ],
    }
)
```

### Table
```python
render_ui(
    surface_id="results",
    title="Search Results",
    component={
        "type": "table",
        "columns": [{"key": "name", "label": "Name"}, {"key": "score", "label": "Score"}],
        "rows": [{"name": "Claude", "score": "92%"}, {"name": "GPT-4o", "score": "88%"}],
    }
)
```

### Form
```python
render_ui(
    surface_id="booking",
    title="Book a Table",
    component={
        "type": "form",
        "action": "confirm_booking",
        "submit_label": "Confirm",
        "fields": [
            {"name": "date", "label": "Date", "type": "text", "required": True},
            {"name": "guests", "label": "Guests", "type": "number"},
        ],
    }
)
```

### Inline quick-actions (inside chat message)
```python
render_ui(
    surface_id="quick_actions",
    target="inline",
    component={
        "type": "stack",
        "children": [
            {"type": "text", "content": "What would you like to do?", "variant": "subheading"},
            {"type": "button", "label": "Deep Analysis", "action": "deep_analysis"},
            {"type": "button", "label": "Skip", "action": "skip", "variant": "secondary"},
        ],
    }
)
```

### Two-column layout
```python
render_ui(
    surface_id="overview",
    component={
        "type": "columns",
        "widths": [1, 2],
        "children": [
            {
                "type": "stack",
                "children": [
                    {"type": "text", "content": "Status", "variant": "subheading"},
                    {"type": "badge", "label": "Active", "color": "success"},
                ]
            },
            {
                "type": "table",
                "columns": [{"key": "k", "label": "Key"}, {"key": "v", "label": "Value"}],
                "rows": [{"k": "CPU", "v": "12%"}, {"k": "RAM", "v": "4.2 GB"}],
            }
        ],
    }
)
```

## Asking for Clarification — Option Selection

**Prefer `render_ui` over plain text when asking the user to choose.** Render an inline surface with one button per option; the user clicks instead of typing, and you get a structured callback.

```python
render_ui(
    surface_id="clarify_tone",
    target="inline",
    component={
        "type": "stack",
        "children": [
            {"type": "text", "content": "What tone should the report use?", "variant": "subheading"},
            {"type": "button", "label": "Formal",   "action": "choose_tone", "context": {"tone": "formal"}},
            {"type": "button", "label": "Casual",   "action": "choose_tone", "context": {"tone": "casual"},   "variant": "secondary"},
            {"type": "button", "label": "Technical", "action": "choose_tone", "context": {"tone": "technical"}, "variant": "secondary"},
        ],
    }
)
```

You will receive: `[canvas: choose_tone] "Formal"` — use `button_label` or `context` to determine the choice.

For binary yes/no confirmations:
```python
{"type": "button", "label": "Yes, proceed", "action": "confirm", "variant": "primary"},
{"type": "button", "label": "Cancel",       "action": "cancel",  "variant": "secondary"},
```

For longer option lists, use `direction: "horizontal"` on the stack to render buttons side by side.

## When to Use Canvas

- Displaying structured data (tables, lists of items with actions)
- Multi-step workflows where you want persistent controls visible alongside chat
- Forms that collect user input before proceeding
- Status dashboards that update as work progresses (upsert the same surface_id)
- **Clarifications**: whenever you'd ask the user to pick from a known set of options — use inline buttons instead of free-text questions
