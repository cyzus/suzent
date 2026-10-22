---
sidebar_position: 2
---

# Canvas (A2UI)

The **Canvas** is a structured UI layer that lets the agent render interactive components — tables, forms, cards, buttons, badges — directly in the Suzent interface, alongside the chat.

The agent calls `render_ui` to push a **surface** (a component tree) to the frontend. The user can interact with it (click buttons, submit forms), and those interactions are sent back to the agent as messages, creating a conversational UI loop.

## Concepts

### Surface

A surface is a named, renderable UI panel. It has:
- **`surface_id`** — a stable slug (e.g. `"search_results"`). Calling `render_ui` with the same id replaces the surface in place (upsert semantics).
- **`component`** — the root of a component tree (see below).
- **`title`** — optional display name shown in the canvas tab strip.
- **`target`** — where to render: `"inline"` (inside the chat message, default) or `"canvas"` (the side panel).

### Component Tree

Components are plain dicts with a `"type"` field. They nest recursively via `"children"` lists.

**Container types** (have `children`):

| Type | Description | Key fields |
|------|-------------|------------|
| `card` | Titled panel with a black header bar | `title`, `children` |
| `stack` | Vertical or horizontal group | `children`, `gap` (`sm`/`md`/`lg`), `direction` |
| `columns` | Side-by-side columns | `children`, `ratios` (list of flex weights) |

**Leaf types**:

| Type | Description | Key fields |
|------|-------------|------------|
| `text` | Paragraph or heading | `content` ⚠️, `variant` (`body`/`heading`/`subheading`/`caption`/`code`) |
| `badge` | Status chip | `label` ⚠️, `color` (`default`/`success`/`warning`/`error`/`info`) |
| `button` | Clickable action | `label` ⚠️, `action` ⚠️, `variant` (`primary`/`secondary`/`danger`), `context`, `disabled` |
| `table` | Data grid | `columns` (list of `{key, label}`), `rows` (list of dicts) |
| `form` | Input form | `action` ⚠️, `submit_label`, `fields` (list of `{name, label, type, required, placeholder, options, default}`) |
| `list` | Bullet or numbered list | `items` (list of strings), `ordered` |
| `progress` | Progress bar | `value` (0–100), `label` |
| `divider` | Horizontal rule | — |
| `html` | Free-form HTML in a sandboxed iframe | `html` ⚠️, `height` (optional, px) |

> ⚠️ **Common mistake:** Do not use `"text"` as a field name — it is not valid for any component. Use:
> - `"content"` for `text` components
> - `"label"` for `badge` and `button` components
>
> Always set `"action"` on buttons and forms so the agent can identify which interaction was triggered.

### Targets

| Target | Behaviour |
|--------|-----------|
| `"inline"` (default) | Embeds the component tree in the current chat message, under a slim header with **Open in side panel** and **Fullscreen** buttons. Persists in message history. |
| `"canvas"` | Renders in the side panel's Canvas tab and leaves a compact pointer card in the chat message to reopen it from. Auto-opens the side panel on the chat's first canvas surface. Use it only for a surface kept in view and updated while the conversation continues (live progress, a dashboard being iterated on). |

Popping an inline surface out copies it into the Canvas tab and focuses it; the inline copy stays where it is.

Layout surfaces for a narrow column (roughly 360–700px): the chat column and the side panel are both about that wide.

### Interaction Callbacks

When the user interacts with a surface, the action is sent back to the agent as a user message:

```
[canvas: <action>] "<button_label>"          # button click
[canvas: <action>] {"field": "value", ...}   # form submit
```

The `action` string is whatever you set in the component's `"action"` field. Always give buttons and forms distinct, descriptive action names.

## Usage

```python
render_ui(
    surface_id="results",
    title="Search Results",
    component={...},
    target="canvas",   # optional, default
)
```

### Example — card with status badges and buttons

```python
render_ui(
    surface_id="status",
    title="Analysis Status",
    component={
        "type": "card",
        "title": "WorldReasoner Results",
        "children": [
            {"type": "text", "content": "Evaluation complete."},
            {"type": "badge", "label": "92% Accuracy", "color": "success"},
            {"type": "badge", "label": "High Confidence", "color": "info"},
            {"type": "button", "label": "View Details", "action": "view_details"},
            {"type": "button", "label": "Export CSV", "action": "export_csv", "variant": "secondary"},
        ],
    }
)
```

### Example — data table

```python
render_ui(
    surface_id="llm_scores",
    title="LLM Benchmark Scores",
    component={
        "type": "table",
        "columns": [
            {"key": "model", "label": "Model"},
            {"key": "score", "label": "Score"},
            {"key": "category", "label": "Category"},
        ],
        "rows": [
            {"model": "Claude 3.5", "score": "92%", "category": "Reasoning"},
            {"model": "GPT-4o",    "score": "88%", "category": "Reasoning"},
        ],
    }
)
```

### Example — input form

```python
render_ui(
    surface_id="booking",
    title="Book a Table",
    component={
        "type": "form",
        "action": "confirm_booking",
        "submit_label": "Confirm",
        "fields": [
            {"name": "date",   "label": "Date",   "type": "text",   "required": True},
            {"name": "guests", "label": "Guests", "type": "number"},
            {"name": "notes",  "label": "Notes",  "type": "textarea"},
        ],
    }
)
# When submitted, agent receives: [canvas: confirm_booking] {"date": "...", "guests": 2, "notes": "..."}
```

### Example — inline quick-action panel

```python
render_ui(
    surface_id="quick_actions",
    target="inline",
    component={
        "type": "stack",
        "children": [
            {"type": "text", "content": "Choose an action:", "variant": "subheading"},
            {"type": "button", "label": "Run Deep Analysis", "action": "deep_analysis"},
            {"type": "button", "label": "Skip",              "action": "skip", "variant": "secondary"},
        ],
    }
)
```

### Example — multi-column layout

```python
render_ui(
    surface_id="dashboard",
    title="Dashboard",
    component={
        "type": "columns",
        "ratios": [2, 1],
        "children": [
            {
                "type": "card",
                "title": "Progress",
                "children": [
                    {"type": "progress", "label": "Data collection", "value": 80},
                    {"type": "progress", "label": "Analysis",        "value": 45},
                ],
            },
            {
                "type": "stack",
                "children": [
                    {"type": "badge", "label": "Running", "color": "warning"},
                    {"type": "button", "label": "Stop", "action": "stop_job", "variant": "danger"},
                ],
            },
        ],
    }
)
```

## Free-form HTML (`html` component)

### Shared presentation

Chat and Canvas share one live renderer per surface ID. `target` selects its
initial placement; moving it later changes its location without creating a
second renderer. The transcript keeps a compact pointer with “Show here” while
the surface is in Canvas. Fullscreen expands the existing sidebar using the
same state as dragging it across the chat; shrinking restores its docked width.
Opening fullscreen from chat first moves the surface to Canvas. Switching
Canvas tabs parks inactive renderers.

The shared provider is scoped to the chat. Connected DOM nodes move using
`Element.moveBefore` where supported, preserving iframe state as well as React
form state. Older webviews fall back to `appendChild`: React state survives,
but those engines may reload an iframe when reparenting it.

When the typed components can't express what you need — charts, SVG diagrams, custom dashboards, interactive prototypes — use the `html` component. It renders a self-contained HTML document in a **sandboxed iframe**.

| Field | Type | Description |
|-------|------|-------------|
| `html` | `str` | Self-contained HTML. May be a full document or a bare fragment. |
| `height` | `int \| None` | Fixed height in px. When omitted, the iframe **auto-sizes** to its content. |

Document-style HTML (news, reports, articles) should omit `height`. The resize
reporter measures the body independently of the iframe viewport, including
content changes, image loads and fonts, so it can grow past 4000px and shrink
when the panel widens. Canvas owns scrolling and its header stays outside the
scrollable body. A standalone HTML surface uses the document's own spacing,
without an extra iframe border or Canvas padding.

Viewport-based applications (maps, editors, dashboards) should set `height`.
For a standalone fixed-height HTML surface, Canvas limits the iframe to the
available panel height and leaves scrolling inside it. Nested fixed-height
HTML components retain their own scroll region within the surrounding document.

### Sandbox model

The HTML runs with `sandbox="allow-scripts"` (and **not** `allow-same-origin`):

- **Scripts run** — so charting libraries, animations, and interactive controls work.
- **Isolated from the host** — no access to the app's cookies, `localStorage`, or parent DOM. It cannot read or modify the rest of Suzent.

This is the same trust level Suzent uses to preview agent-authored `.html` files.

### Sending feedback back to the agent

Because the iframe is isolated, interactive HTML talks back to the agent via `postMessage`. Post a message to `window.parent` with this shape:

```js
window.parent.postMessage(
  { type: 'a2ui:action', action: 'my_action', context: { /* any JSON */ } },
  '*'
);
```

The host validates the message (shape + origin) and delivers it to the agent exactly like a button click or form submit:

```
[canvas: my_action] {"...": "..."}
```

So a button, chart click, or form inside your HTML can drive the conversation. Use distinct, descriptive `action` names just like with `button`/`form` components.

> The host also injects a tiny script that reports content height for auto-sizing. You don't need to add it — just emit your HTML.

### Example — HTML dashboard with a feedback button

```python
render_ui(
    surface_id="london_food_plan",
    title="London Food Plan",
    component={
        "type": "html",
        "html": """
            <div style="font-family: monospace; padding: 16px;">
              <h2>London Food Plan</h2>
              <p>Status: <strong>Ready to book</strong></p>
              <button onclick="
                window.parent.postMessage(
                  {type:'a2ui:action', action:'start_booking_bot',
                   context:{stage:'stage_2_reservations'}}, '*')
              ">Start Auto-Booking</button>
            </div>
        """,
    }
)
# When the button is clicked, the agent receives:
# [canvas: start_booking_bot] {"stage": "stage_2_reservations"}
```

### When to use `html` vs typed components

- Prefer **typed components** (`table`, `form`, `button`, …) for simple, structured UI that talks back — they're styled to match Suzent and validated by the schema.
- Reach for **`html`** when you need rich visuals or layouts the vocabulary can't express. Both render in the same canvas and support the same `{action, context}` feedback loop, so you can mix them across surfaces.

## Ask Question Tool

For collecting user input during a task, prefer `ask_question` over `render_ui`. It blocks the agent until the user responds, then returns the answers as structured data.

```python
ask_question(questions=[
    QuestionItem(question="What's your goal?", options=["Build a feature", "Fix a bug", "Refactor"], required=True),
    QuestionItem(question="Any additional context?"),
])
# Returns: User answered: {"what_s_your_goal": "Fix a bug", "any_additional_context": "..."}
```

### Rendering Behaviour

Every call renders as a paged form, one question per page:

| Shape | Field |
|-------|-------|
| `options`, no `multi_select` | Single-select list |
| `options` + `multi_select=True` | Checkbox list |
| No `options` | Free-text `textarea` |

### QuestionItem Fields

| Field | Type | Description |
|-------|------|-------------|
| `question` | `str` | The question text |
| `options` | `list[str] \| None` | Selectable choices |
| `multi_select` | `bool` | Allow multiple selections (checkbox list) |
| `field_name` | `str` | Response key (auto-slugged from question if omitted) |
| `required` | `bool` | Mark the field required |

### Paged Form UX

When rendered as a form, `ask_question` shows one question at a time with **Back**, **Skip**, and **Next/Submit** navigation. The user can skip optional questions; **Next** is only enabled once the current field has a value.

Every `select` and `multiselect` field ends with a "Type something else…" item, which expands a text input on the same page. Each question keeps its own free-text state, so moving to the next page starts empty.

Keyboard: number keys `1`–`9` pick (or toggle) the option with that badge, including the "something else" item; `Enter` moves to the next question or submits (`Shift+Enter` adds a newline in a textarea); `Esc` leaves the free-text input so number keys work again.

### Callback

- Form submit → `[canvas: submit_question] {"field": "value", ...}`
  - Single-select → `string`; multi-select → `list[str]`; textarea → `string`

## Canvas Persistence

Canvas surfaces are persisted to `localStorage` keyed by chat ID. They survive page reloads and are restored when switching back to a conversation.

## Upsert Semantics

Calling `render_ui` with the same `surface_id` **replaces** the existing surface. There is no `remove_ui` — to clear a surface, replace it with an empty stack or stop sending updates.

- In the Canvas tab, the surface is replaced in place.
- Within one turn, the inline part is replaced in place, so live progress updates rather than stacking copies.
- Across turns, the new version renders at the latest message. Every render carries a `rev` (milliseconds, stamped by `render_ui`), and an inline copy collapses to a one-line "updated later" row with a **Show** toggle once a copy of the same id with a larger `rev` is mounted. Copies saved before `rev` existed never collapse.
