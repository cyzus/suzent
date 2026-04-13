"""
RenderUITool — push structured A2UI surfaces to the frontend canvas.

Agents call render_ui() to display rich interactive components (tables, forms,
cards, buttons) in the canvas panel alongside the chat. The same surface_id
performs an upsert: calling again with the same id replaces the existing surface.
"""

from typing import Any, Annotated, Literal, TypedDict, NotRequired

from pydantic import Field

from pydantic_ai import RunContext

from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.core.agent_deps import AgentDeps


class UIComponent(TypedDict):
    """Structured UI component tree."""

    type: Literal[
        "card",
        "stack",
        "columns",
        "text",
        "badge",
        "button",
        "table",
        "form",
        "list",
        "progress",
        "divider",
    ]
    children: NotRequired[list["UIComponent"]]
    content: NotRequired[str]
    label: NotRequired[str]
    action: NotRequired[str]
    variant: NotRequired[str]
    color: NotRequired[str]
    columns: NotRequired[list[dict[str, Any]]]
    rows: NotRequired[list[dict[str, Any]]]
    fields: NotRequired[list[dict[str, Any]]]
    items: NotRequired[list[Any]]
    value: NotRequired[Any]
    props: NotRequired[dict[str, Any]]


class RenderUITool(Tool):
    name = "RenderUITool"
    tool_name = "render_ui"
    group = ToolGroup.AGENT
    requires_approval = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        surface_id: Annotated[
            str,
            Field(
                description="Stable surface id. Reusing the same id replaces the existing surface."
            ),
        ],
        component: Annotated[
            UIComponent, Field(description="Structured UI component tree to render.")
        ],
        title: Annotated[
            str,
            Field(
                default="", description="Optional panel title; defaults to surface_id."
            ),
        ] = "",
        target: Annotated[
            Literal["canvas", "inline"],
            Field(
                description="Where to render the surface: sidebar canvas or inline in chat."
            ),
        ] = "canvas",
    ) -> ToolResult:
        """Render a structured UI surface in the canvas panel or inline in chat.

        Interactions are returned as: [canvas: <action>] "<button_label>"
        Always set "action" on buttons/forms. Use inline buttons to ask the user
        to choose between options instead of plain text questions.

        For full component reference and examples, call: skill_execute("canvas")

        Args:
            surface_id: Stable slug for this surface (e.g. "results", "booking_form").
                        Calling again with the same id replaces the existing surface.
            component:  Component tree dict. Root must have a "type" field.
                        Containers (have "children"): card, stack, columns.
                        Leaves: text (content+variant), badge (label+color),
                                button (label+action+variant+context), table
                                (columns+rows), form (action+fields), list
                                (items), progress (value 0-100), divider.
                        CRITICAL: use "label" for buttons/badges, "content" for
                        text — never "text" as a field name or components appear empty.
            title:      Tab strip label (defaults to surface_id).
            target:     "canvas" (sidebar, default) or "inline" (inside chat message).

        """
        if not surface_id.strip():
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "surface_id is required.",
            )

        if ctx.deps.a2ui_queue is not None:
            await ctx.deps.a2ui_queue.put(
                {
                    "event": "a2ui.render",
                    "id": surface_id,
                    "title": title or surface_id,
                    "component": component,
                    "target": target if target in ("canvas", "inline") else "canvas",
                }
            )
            location = "inline in chat" if target == "inline" else "canvas"
            return ToolResult.success_result(
                f"Surface '{surface_id}' rendered {location}.",
                metadata={
                    "surface_id": surface_id,
                    "target": target,
                    "title": title or surface_id,
                },
            )

        # Fallback: if no queue (e.g. CLI/headless), return an error
        return ToolResult.error_result(
            ToolErrorCode.EXECUTION_FAILED,
            f"Cannot render UI: Canvas not available in this environment. Surface '{surface_id}' failed.",
            metadata={
                "surface_id": surface_id,
                "target": target,
                "title": title or surface_id,
            },
        )
