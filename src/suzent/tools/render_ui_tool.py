"""
RenderUITool — push structured A2UI surfaces to the frontend canvas.

Agents call render_ui() to display rich interactive components (tables, forms,
cards, buttons) in the canvas panel alongside the chat. The same surface_id
performs an upsert: calling again with the same id replaces the existing surface.
"""

from typing import Any, Annotated

from pydantic import Field, TypeAdapter, ValidationError
from pydantic_ai import RunContext

from suzent.a2ui.models import A2UISurface
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult


_SURFACE_ADAPTER = TypeAdapter(A2UISurface)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _surface_payload(
    *,
    surface_id: Any,
    component: Any,
    title: Any,
    target: Any,
    id: Any,
    extra: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(extra.get("surface"), dict) and component is None:
        return dict(extra["surface"])

    sid = _as_text(surface_id or id or extra.get("surfaceId") or title).strip()
    return {
        "id": sid or "ui",
        "title": _as_text(title).strip() or None,
        "component": component,
        "target": target,
    }


class RenderUITool(Tool):
    name = "RenderUITool"
    tool_name = "render_ui"
    group = ToolGroup.AGENT
    requires_approval = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        surface_id: Annotated[
            Any,
            Field(
                default=None,
                description="Stable surface id. Reusing the same id replaces the existing surface.",
            ),
        ] = None,
        component: Annotated[
            Any,
            Field(
                default=None,
                description="A2UI component tree. Root must include a valid 'type' discriminator.",
            ),
        ] = None,
        title: Annotated[
            Any,
            Field(
                default="",
                description="Optional panel title; defaults to surface_id.",
            ),
        ] = "",
        target: Annotated[
            Any,
            Field(
                default="canvas",
                description="Where to render the surface: 'canvas' or 'inline'.",
            ),
        ] = "canvas",
        id: Annotated[
            Any,
            Field(default=None, description="Alias for surface_id."),
        ] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Render a structured UI surface in the canvas panel or inline in chat.

        The A2UI schema is defined in suzent.a2ui.models. Use `content` for text
        components, `label` and `action` for buttons, and `columns` plus `rows`
        for tables. The `id` alias is accepted for compatibility with A2UISurface.
        """
        try:
            surface = _SURFACE_ADAPTER.validate_python(
                _surface_payload(
                    surface_id=surface_id,
                    component=component,
                    title=title,
                    target=target,
                    id=id,
                    extra=kwargs,
                )
            )
        except ValidationError as exc:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Invalid A2UI surface. Fix the render_ui arguments and try again.",
                metadata={"errors": exc.errors(include_url=False)},
            )

        payload = surface.model_dump(exclude_none=True)
        sid = surface.id
        target_value = surface.target
        title_value = surface.title or sid
        payload["title"] = title_value

        if ctx.deps.a2ui_queue is not None:
            await ctx.deps.a2ui_queue.put({"event": "a2ui.render", **payload})
            location = "inline in chat" if target_value == "inline" else "canvas"
            return ToolResult.success_result(
                f"Surface '{sid}' rendered {location}.",
                metadata={
                    "surface_id": sid,
                    "target": target_value,
                    "title": title_value,
                },
            )

        return ToolResult.error_result(
            ToolErrorCode.EXECUTION_FAILED,
            f"Cannot render UI: Canvas not available in this environment. Surface '{sid}' failed.",
            metadata={
                "surface_id": sid,
                "target": target_value,
                "title": title_value,
            },
        )
