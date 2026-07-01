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
| `html` | `html`, `height` | free-form HTML in a sandboxed iframe — for charts, SVG, custom dashboards the other types can't express |

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

## Free-form HTML (`html` component)

When the typed components can't express what you need — charts, SVG diagrams, custom dashboards, interactive prototypes — use the `html` component. It renders self-contained HTML in a **sandboxed iframe** (scripts run, but isolated from the app: no cookies, storage, or parent-DOM access). Omit `height` to auto-size, or set it (px) for a fixed height.

```python
render_ui(
    surface_id="chart",
    title="Weekly Traffic",
    component={
        "type": "html",
        "html": """
            <div style="font-family: monospace; padding: 16px;">
              <h2>Weekly Traffic</h2>
              <svg width="300" height="100">
                <rect x="0"   y="40" width="40" height="60" fill="black"/>
                <rect x="60"  y="20" width="40" height="80" fill="black"/>
                <rect x="120" y="55" width="40" height="45" fill="black"/>
              </svg>
              <button onclick="
                window.parent.postMessage(
                  {type:'a2ui:action', action:'refresh_chart', context:{range:'30d'}}, '*')
              ">Load 30 days</button>
            </div>
        """,
    }
)
```

**Feedback from HTML → you.** Because the iframe is isolated, interactive HTML sends actions back via `postMessage`. Have your HTML post to `window.parent`:

```js
window.parent.postMessage(
  {type: 'a2ui:action', action: 'my_action', context: {/* any JSON */}}, '*');
```

You receive it exactly like a button click: `[canvas: my_action] {...}`. So buttons, chart clicks, or forms inside your HTML can drive the conversation — use distinct `action` names just like with `button`/`form`.

**Prefer typed components** (`table`, `form`, `button`, …) for simple structured UI that talks back — they match the app's style and are schema-validated. Reach for `html` only when you need visuals or layouts the vocabulary can't express.

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
- **Rich visuals** (charts, SVG diagrams, custom layouts) the typed components can't express — use the `html` component
- **Clarifications**: whenever you'd ask the user to pick from a known set of options — use inline buttons instead of free-text questions
