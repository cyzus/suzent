"""
A2UI component models for structured agent-to-UI rendering.

Agents describe UI surfaces as nested component trees using these Pydantic models.
The frontend's A2UIRenderer maps each type to its React component.

Component hierarchy:
  Leaf:       A2UIText, A2UIBadge, A2UIButton, A2UITable, A2UIForm,
              A2UIList, A2UIProgress, A2UIDivider
  Container:  A2UICard, A2UIColumns, A2UIStack  (hold children[])
  Top-level:  A2UISurface  (id + root component)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── Leaf Components ────────────────────────────────────────────────────


class A2UIText(BaseModel):
    """Plain text block with typographic variants."""

    type: Literal["text"] = "text"
    content: str
    variant: Literal["body", "heading", "subheading", "caption", "code"] = "body"


class A2UIBadge(BaseModel):
    """Inline colored label chip."""

    type: Literal["badge"] = "badge"
    label: str
    color: Literal["default", "success", "warning", "error", "info"] = "default"


class A2UIButton(BaseModel):
    """Clickable action button. Sends {action, context} back to agent."""

    type: Literal["button"] = "button"
    label: str
    action: str
    context: dict[str, Any] = Field(default_factory=dict)
    variant: Literal["primary", "secondary", "danger"] = "primary"
    disabled: bool = False


class A2UITableColumn(BaseModel):
    """Column definition for A2UITable."""

    key: str
    label: str
    width: Optional[str] = None


class A2UITable(BaseModel):
    """Data table with defined columns and row dicts."""

    type: Literal["table"] = "table"
    columns: list[A2UITableColumn]
    rows: list[dict[str, Any]]


class A2UIFormField(BaseModel):
    """Single field within a form."""

    name: str
    label: str
    type: Literal["text", "number", "select", "checkbox", "textarea"] = "text"
    options: list[str] = Field(default_factory=list)  # for select fields
    required: bool = False
    default: Any = None
    placeholder: str = ""


class A2UIForm(BaseModel):
    """Form with labeled fields. Sends {action, data} back to agent on submit."""

    type: Literal["form"] = "form"
    fields: list[A2UIFormField]
    submit_label: str = "Submit"
    action: str


class A2UIList(BaseModel):
    """Ordered or unordered list of string items."""

    type: Literal["list"] = "list"
    items: list[str]
    ordered: bool = False


class A2UIProgress(BaseModel):
    """Progress bar, value 0–100."""

    type: Literal["progress"] = "progress"
    value: float
    label: Optional[str] = None


class A2UIDivider(BaseModel):
    """Horizontal rule separator."""

    type: Literal["divider"] = "divider"


# ── Container Components ───────────────────────────────────────────────
# Forward references resolved via model_rebuild() after all classes are defined.


class A2UICard(BaseModel):
    """Titled card container with arbitrary children."""

    type: Literal["card"] = "card"
    title: Optional[str] = None
    children: list[A2UIComponent]  # type: ignore[name-defined]


class A2UIColumns(BaseModel):
    """Horizontal flex layout. ratios=[1,2] gives 1:2 column widths."""

    type: Literal["columns"] = "columns"
    children: list[A2UIComponent]  # type: ignore[name-defined]
    ratios: Optional[list[float]] = None


class A2UIStack(BaseModel):
    """Vertical flex stack with configurable gap."""

    type: Literal["stack"] = "stack"
    children: list[A2UIComponent]  # type: ignore[name-defined]
    gap: Literal["sm", "md", "lg"] = "md"


# ── Union Type ─────────────────────────────────────────────────────────

A2UIComponent = Annotated[
    Union[
        A2UIText,
        A2UIBadge,
        A2UIButton,
        A2UITable,
        A2UIForm,
        A2UIList,
        A2UIProgress,
        A2UIDivider,
        A2UICard,
        A2UIColumns,
        A2UIStack,
    ],
    Field(discriminator="type"),
]

# Resolve forward references in container models
A2UICard.model_rebuild()
A2UIColumns.model_rebuild()
A2UIStack.model_rebuild()


# ── Top-level Surface ──────────────────────────────────────────────────


class A2UISurface(BaseModel):
    """
    Top-level canvas surface.

    id:        Stable identifier. Calling render_ui with the same id replaces (upserts)
               the existing surface in the canvas.
    title:     Optional display title shown in the canvas tab strip.
    component: Root component — can be any A2UIComponent, typically a Card or Stack
               to group multiple sub-components.
    target:    "canvas" (default) renders in the sidebar canvas panel.
               "inline" renders the surface directly inside the chat message.
    """

    id: str
    title: Optional[str] = None
    component: A2UIComponent
    target: Literal["canvas", "inline"] = "canvas"
