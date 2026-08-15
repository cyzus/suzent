# A2UI component reference

## Tool shape

```text
render_ui(surface_id, component, title="", target="canvas")
```

`target` is `canvas` or `inline`. Calling the tool again with the same `surface_id`
replaces the existing surface.

## Containers

| Type | Fields | Purpose |
|---|---|---|
| `card` | `title`, `children` | Titled bordered panel |
| `stack` | `children`, optional `direction` | Vertical or horizontal group |
| `columns` | `children`, optional `widths` | Side-by-side layout |

## Leaves

| Type | Important fields |
|---|---|
| `text` | `content`, optional `variant` |
| `badge` | `label`, optional `color` |
| `button` | `label`, `action`, optional `variant`, `context` |
| `table` | `columns: [{key, label}]`, `rows` |
| `form` | `action`, `submit_label`, `fields` |
| `list` | `items`, optional `ordered` |
| `progress` | `value` from 0 to 100, optional `label` |
| `divider` | no additional fields |
| `html` | `html`, optional `height` |

Text variants include `body`, `heading`, `subheading`, `caption`, and `code`. Common
badge colors are `success`, `warning`, `error`, `info`, and `default`. Button variants
are `primary`, `secondary`, and `danger`.

Form field types include `text`, `number`, `textarea`, and `select`. Give every field a
stable `name` and user-facing `label`.

## Examples

### Status card

```python
render_ui(
    surface_id="analysis-status",
    title="Analysis",
    component={
        "type": "card",
        "title": "Result",
        "children": [
            {"type": "text", "content": "Evaluation complete."},
            {"type": "badge", "label": "Passed", "color": "success"},
            {
                "type": "button",
                "label": "Export",
                "action": "export_result",
                "context": {"format": "csv"},
            },
        ],
    },
)
```

### Inline form

```python
render_ui(
    surface_id="report-options",
    target="inline",
    component={
        "type": "form",
        "action": "generate_report",
        "submit_label": "Generate",
        "fields": [
            {"name": "title", "label": "Title", "type": "text", "required": True},
            {
                "name": "detail",
                "label": "Detail",
                "type": "select",
                "options": ["Summary", "Full"],
            },
        ],
    },
)
```

## HTML actions

Use `html` only when typed components cannot express the visualization. Send an action
back to Suzent with a minimal payload:

```javascript
window.parent.postMessage(
  {type: "a2ui:action", action: "select_point", context: {id: "p42"}},
  "*"
);
```

The agent receives the event as `[canvas: select_point]`. Do not place credentials,
private data, or executable content obtained from an untrusted page into the HTML.
