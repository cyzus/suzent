# A2UI component reference

## Tool shape

`render_ui` takes these arguments. They are JSON arguments, not Python:

| Argument | Type | Notes |
|---|---|---|
| `surface_id` | string | Stable id. Calling again with the same id replaces the surface. |
| `component` | **JSON object** | The root component. Never a string, never a list. |
| `title` | string, optional | Panel title; defaults to `surface_id`. |
| `target` | `"inline"` or `"canvas"` | `inline` (default) renders in the chat; `canvas` is the side panel, for a surface kept in view while the conversation continues. |

An inline surface reappears at the latest message when re-rendered and the older copy
collapses.

## The one rule: every node is an object with a `type`

```json
{"type": "text", "content": "Hello"}
```

- `component` is a single JSON **object**. Do not wrap it in quotes, do not stringify it.
- Every node, including each entry of `children`, is an object with a `type`.
- `children` holds **objects**, never ids, indexes or names. `[0, 1]`, `["a", "b"]` and
  `[null]` are all invalid. There is no component registry to point into.
- Put every field inside `component`. Do not spread `type`/`children` next to `surface_id`.
- Text uses `content` (not `text`); badges and buttons use `label`.

## Containers

| Type | Fields | Purpose |
|---|---|---|
| `card` | `title`, `children` | Titled bordered panel |
| `stack` | `children`, `gap` (`sm`, `md`, `lg`) | Vertical group |
| `columns` | `children`, `ratios` (e.g. `[1, 2]`) | Side-by-side layout |

## Leaves

| Type | Required | Optional |
|---|---|---|
| `text` | `content` | `variant` (`body`, `heading`, `subheading`, `caption`, `code`), `markdown` |
| `badge` | `label` | `color` (`default`, `success`, `warning`, `error`, `info`) |
| `button` | `label`, `action` | `variant` (`primary`, `secondary`, `danger`), `context` (object), `disabled` |
| `table` | `columns: [{key, label}]`, `rows: [{<key>: value}]` | `columns[].width` |
| `form` | `action`, `fields` | `submit_label`, `paged` |
| `list` | `items` (strings) | `ordered` |
| `progress` | `value` (0 to 100) | `label` |
| `divider` | | |
| `html` | `html` | `height` (px; omit to auto-size) |

Form fields are objects: `name`, `label`, optional `type` (`text`, `number`, `select`,
`multiselect`, `checkbox`, `textarea`), `options` (strings, for select), `required`,
`placeholder`, `allow_free_text`.

## Choosing typed components or HTML

- **Typed components** for simple, semantic controls: a status card, a table, a form, a
  few buttons, a progress bar. They match Suzent's styling and are validated precisely.
- **`html`** for what the vocabulary cannot express: charts, SVG diagrams, custom
  dashboards, interactive prototypes. It is a self-contained document in a sandboxed
  iframe.
- Both talk back the same way: a typed `button`/`form` or an HTML `postMessage` becomes a
  `[canvas: <action>]` event. Do not rebuild a simple form as HTML just because a typed
  call failed; fix the call using the error message.

## Canonical examples

### Status card (container, children, badge, button with context)

```json
{
  "surface_id": "build-status",
  "title": "Build",
  "component": {
    "type": "card",
    "title": "Build",
    "children": [
      {"type": "text", "content": "CI finished", "variant": "heading"},
      {"type": "text", "content": "All 1212 tests passed"},
      {"type": "badge", "label": "PASS", "color": "success"},
      {
        "type": "button",
        "label": "Open report",
        "action": "open_report",
        "context": {"run_id": 42}
      }
    ]
  }
}
```

### Table with a caption

```json
{
  "surface_id": "servers",
  "component": {
    "type": "stack",
    "children": [
      {
        "type": "table",
        "columns": [
          {"key": "name", "label": "Name"},
          {"key": "region", "label": "Region"},
          {"key": "cpu", "label": "CPU %"}
        ],
        "rows": [
          {"name": "alpha", "region": "eu", "cpu": 12},
          {"name": "beta", "region": "us", "cpu": 57}
        ]
      },
      {"type": "text", "content": "updated just now", "variant": "caption"}
    ]
  }
}
```

### Inline form

```json
{
  "surface_id": "trip",
  "target": "inline",
  "component": {
    "type": "form",
    "action": "plan_trip",
    "submit_label": "Plan",
    "fields": [
      {"name": "destination", "label": "Destination", "type": "text", "required": true},
      {"name": "nights", "label": "Nights", "type": "number"},
      {
        "name": "class",
        "label": "Class",
        "type": "select",
        "options": ["economy", "business"]
      },
      {"name": "notes", "label": "Notes", "type": "textarea"}
    ]
  }
}
```

### Canvas dashboard (columns, nested containers, progress, list)

```json
{
  "surface_id": "ops",
  "target": "canvas",
  "title": "Ops",
  "component": {
    "type": "columns",
    "ratios": [1, 1],
    "children": [
      {
        "type": "card",
        "title": "Queue",
        "children": [
          {"type": "progress", "value": 64, "label": "processed"},
          {"type": "list", "items": ["job-17", "job-18", "job-21"]}
        ]
      },
      {
        "type": "card",
        "title": "Alerts",
        "children": [
          {"type": "badge", "label": "disk 85%", "color": "warning"},
          {"type": "button", "label": "Purge cache", "action": "purge_cache", "variant": "danger"}
        ]
      }
    ]
  }
}
```

### HTML (charts, SVG, custom layouts)

```json
{
  "surface_id": "latency-chart",
  "component": {
    "type": "html",
    "height": 320,
    "html": "<!doctype html><html><body><svg viewBox='0 0 100 40' width='100%'><polyline fill='none' stroke='#000' points='0,30 25,12 50,20 75,5 100,15'/></svg><button onclick=\"window.parent.postMessage({type:'a2ui:action',action:'select_point',context:{id:'p42'}},'*')\">Select</button></body></html>"
  }
}
```

## HTML actions

Send an action back to Suzent with a minimal JSON payload:

```javascript
window.parent.postMessage(
  {type: "a2ui:action", action: "select_point", context: {id: "p42"}},
  "*"
);
```

The agent receives the event as `[canvas: select_point]`. Do not place credentials,
private data, or executable content obtained from an untrusted page into the HTML.

## Reading errors

A rejected call returns one line per problem with the path to the bad field, for example:

```text
- component.card.children.0: Input should be a valid dictionary or object ... (expected a JSON object with a 'type', not a string, number or index)
- component.stack.children.1.button.action: Field required
```

Fix exactly those fields and call `render_ui` again with the same `surface_id`. A
`component` sent as a JSON-encoded string of an object is still accepted for
compatibility but is deprecated; any other string is rejected and is never treated as
HTML or text.
