"""
Model-facing schema and argument coercion for the ``render_ui`` tool.

``A2UIComponent`` (see ``models.py``) is the source of truth for what a surface
may contain. It is a recursive discriminated union, which providers handle very
differently when it is sent as a tool schema: some reject ``$defs``/recursive
``$ref``, others accept it but then stream the whole tree as a JSON *string*.
Leaving the ``component`` parameter untyped (the previous behaviour) was worse
-- the model saw ``{}`` and had to guess, so Anthropic models sent the tree as a
string and Gemini models sent ``children: [0, 1]`` index lists.

``COMPONENT_TOOL_SCHEMA`` is a *flat*, provider-neutral JSON Schema for one
component node: an ``object`` with a ``type`` enum and every field any component
uses, each documented with the component it belongs to. Nested children are
declared as objects with a required ``type``, so nothing recursive reaches the
provider. Validation is still done by ``A2UISurface`` -- this schema only tells
the model the shape. ``tests/a2ui/test_render_ui_schema.py`` keeps it from
drifting from the Pydantic models.
"""

from __future__ import annotations

import copy
import json
from typing import Any, get_args

from suzent.a2ui.models import A2UIComponent


def component_types() -> tuple[str, ...]:
    """The ``type`` discriminator values of every A2UI component, in union order."""
    union = get_args(A2UIComponent)[0]
    return tuple(cls.model_fields["type"].default for cls in get_args(union))


_CHILD_NODE: dict[str, Any] = {
    "type": "object",
    "description": (
        "A child component OBJECT with the same shape as its parent "
        "(always has a 'type'). Not an id, an index or a string."
    ),
    "properties": {"type": {"type": "string", "enum": list(component_types())}},
    "required": ["type"],
}

_NODE_PROPERTIES: dict[str, Any] = {
    "type": {
        "type": "string",
        "enum": list(component_types()),
        "description": "Component kind. Required on every node.",
    },
    "content": {
        "type": "string",
        "description": "text: the text to show (use 'content', never 'text').",
    },
    "markdown": {"type": "boolean", "description": "text: render content as markdown."},
    "variant": {
        "type": "string",
        "enum": [
            "body",
            "heading",
            "subheading",
            "caption",
            "code",
            "primary",
            "secondary",
            "danger",
        ],
        "description": (
            "text: body|heading|subheading|caption|code. "
            "button: primary|secondary|danger."
        ),
    },
    "label": {
        "type": "string",
        "description": "badge/button: the visible label. progress: optional caption.",
    },
    "color": {
        "type": "string",
        "enum": ["default", "success", "warning", "error", "info"],
        "description": "badge: color.",
    },
    "action": {
        "type": "string",
        "description": (
            "button/form: stable action name returned to the agent as "
            "'[canvas: <action>]'. Required for button and form."
        ),
    },
    "context": {
        "type": "object",
        "description": "button: JSON object of identifiers sent back with the action.",
    },
    "disabled": {"type": "boolean", "description": "button: disable the button."},
    "title": {"type": "string", "description": "card: optional title."},
    "children": {
        "type": "array",
        "items": _CHILD_NODE,
        "description": "card/columns/stack: child component objects.",
    },
    "gap": {
        "type": "string",
        "enum": ["sm", "md", "lg"],
        "description": "stack: spacing between children.",
    },
    "ratios": {
        "type": "array",
        "items": {"type": "number"},
        "description": "columns: relative widths, e.g. [1, 2].",
    },
    "columns": {
        "type": "array",
        "description": "table: column definitions.",
        "items": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key used in each row."},
                "label": {"type": "string", "description": "Header text."},
                "width": {"type": "string", "description": "Optional CSS width."},
            },
            "required": ["key", "label"],
        },
    },
    "rows": {
        "type": "array",
        "items": {"type": "object"},
        "description": "table: one object per row, keyed by column 'key'.",
    },
    "fields": {
        "type": "array",
        "description": "form: input fields.",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Stable field key."},
                "label": {"type": "string", "description": "User-facing label."},
                "type": {
                    "type": "string",
                    "enum": [
                        "text",
                        "number",
                        "select",
                        "multiselect",
                        "checkbox",
                        "textarea",
                    ],
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "select/multiselect choices.",
                },
                "allow_free_text": {"type": "boolean"},
                "required": {"type": "boolean"},
                "placeholder": {"type": "string"},
            },
            "required": ["name", "label"],
        },
    },
    "submit_label": {"type": "string", "description": "form: submit button text."},
    "paged": {"type": "boolean", "description": "form: show one field per page."},
    "items": {
        "type": "array",
        "items": {"type": "string"},
        "description": "list: the item strings.",
    },
    "ordered": {
        "type": "boolean",
        "description": "list: numbered instead of bulleted.",
    },
    "value": {"type": "number", "description": "progress: 0-100."},
    "html": {
        "type": "string",
        "description": (
            "html: a self-contained HTML document, rendered in a sandboxed iframe."
        ),
    },
    "height": {
        "type": "integer",
        "description": "html: optional fixed height in px; omit to auto-size.",
    },
}

COMPONENT_DESCRIPTION = (
    "The component tree: ONE JSON OBJECT (not a string) whose 'type' is one of "
    + ", ".join(component_types())
    + ". Containers (card, columns, stack) hold child objects in 'children'. "
    'Example: {"type": "card", "title": "Build", "children": [{"type": "text", '
    '"content": "All tests passed"}, {"type": "button", "label": "Open report", '
    '"action": "open_report", "context": {"run_id": 42}}]}'
)


def component_tool_schema() -> dict[str, Any]:
    """A fresh copy of the provider-neutral JSON Schema for the ``component`` parameter."""
    return {
        "type": "object",
        "description": COMPONENT_DESCRIPTION,
        "properties": copy.deepcopy(_NODE_PROPERTIES),
        "required": ["type"],
    }


class ComponentArgumentError(ValueError):
    """``component`` was not usable; the message is written for the model."""


_STRING_HINT = (
    "Send `component` as a JSON object, e.g. "
    '{"type": "text", "content": "Hello"}. '
    'For free-form HTML use {"type": "html", "html": "<h1>Hi</h1>"}.'
)


def coerce_component(value: Any) -> tuple[Any, bool]:
    """Normalise the ``component`` argument; returns ``(component, was_json_string)``.

    Objects (and anything else) pass through untouched for ``A2UISurface`` to
    validate. A string is accepted only when it is a JSON *object* -- some
    providers stream a nested argument as an encoded string -- and the caller
    is told so it can log a deprecation. Any other string is rejected with an
    explanation instead of being guessed at (it is never treated as HTML or text).
    """
    if not isinstance(value, str):
        return value, False

    stripped = value.strip()
    if not stripped:
        raise ComponentArgumentError(f"`component` is an empty string. {_STRING_HINT}")
    if not stripped.startswith("{"):
        raise ComponentArgumentError(
            f"`component` must be a JSON object but was a plain string. {_STRING_HINT}"
        )
    try:
        parsed = json.loads(stripped)
    except (ValueError, RecursionError) as exc:
        raise ComponentArgumentError(
            f"`component` was a string that is not valid JSON ({exc}). {_STRING_HINT}"
        ) from None
    if not isinstance(parsed, dict):  # pragma: no cover - startswith("{") implies dict
        raise ComponentArgumentError(
            f"`component` must be a JSON object, not {type(parsed).__name__}. "
            f"{_STRING_HINT}"
        )
    return parsed, True
