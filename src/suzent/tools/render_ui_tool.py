"""
RenderUITool — push structured A2UI surfaces to the frontend.

Agents call render_ui() to display rich interactive components (tables, forms,
cards, buttons) inside the chat, or in the side panel canvas. The same surface_id
performs an upsert: calling again with the same id replaces the existing surface.
"""

import time
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError, WithJsonSchema
from pydantic_ai import RunContext

from suzent.a2ui.models import A2UISurface
from suzent.a2ui.schema import (
    ComponentArgumentError,
    coerce_component,
    component_tool_schema,
)
from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)

_SURFACE_ADAPTER = TypeAdapter(A2UISurface)

# How many validation problems are spelled out in the message the model reads.
_MAX_REPORTED_ERRORS = 8

_STRING_SCHEMA = {"type": "string"}

# Keys that belong inside ``component``; seen at the top level when a model
# flattens the tree into the call. Only used to make the error message specific.
_COMPONENT_FIELD_NAMES = frozenset(
    {"type", "content", "children", "label", "action", "columns", "rows", "fields"}
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _format_errors(errors: list[dict[str, Any]]) -> str:
    """One readable line per validation problem, with the path to the bad field.

    The raw ``errors`` list is kept in the result metadata, but models act on the
    message, and a pydantic error dict is easy to misread as "try again".
    """
    lines = []
    for err in errors[:_MAX_REPORTED_ERRORS]:
        path = ".".join(str(part) for part in err.get("loc", ())) or "(root)"
        line = f"- {path}: {err.get('msg', 'invalid value')}"
        if err.get("type") in ("model_type", "model_attributes_type", "dict_type"):
            line += (
                " (expected a JSON object with a 'type', not a string, number or index)"
            )
        lines.append(line)
    if len(errors) > _MAX_REPORTED_ERRORS:
        lines.append(f"- ... and {len(errors) - _MAX_REPORTED_ERRORS} more")
    return "\n".join(lines)


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
    # Validation stays lenient on purpose: the surface fields are ``Any`` here.
    # This tool takes whatever the model sends -- extra keys via ``**kwargs``,
    # ``id`` for ``surface_id``, a whole ``surface`` dict -- normalises it in
    # ``_surface_payload`` and validates once against ``A2UISurface``, so a bad
    # call comes back as this tool's own message with the offending fields
    # named, rather than as a schema rejection at the boundary.
    #
    # What the *model sees* is a different matter and is declared explicitly with
    # ``WithJsonSchema``. A bare ``Any`` published ``component`` as ``{}``, so
    # models guessed: Anthropic sent the tree as a JSON string, Gemini sent
    # ``children: [0, 1]``. ``component`` now advertises a flat, provider-neutral
    # object schema (``suzent.a2ui.schema``); the typed ``A2UIComponent`` union is
    # deliberately not sent because its recursive ``$defs`` are rejected by some
    # providers. ``target`` is a closed set of two and is typed as exactly that.
    name = "RenderUITool"
    tool_name = "render_ui"
    group = ToolGroup.INTERACTION
    requires_approval = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        surface_id: Annotated[
            Any,
            WithJsonSchema(_STRING_SCHEMA),
            Field(
                description="Stable surface id. Reusing the same id replaces the existing surface.",
            ),
        ] = None,
        component: Annotated[
            Any,
            WithJsonSchema(component_tool_schema()),
        ] = None,
        title: Annotated[
            Any,
            WithJsonSchema(_STRING_SCHEMA),
            Field(
                description="Optional panel title; defaults to surface_id.",
            ),
        ] = "",
        target: Annotated[
            Literal["canvas", "inline"],
            Field(
                description=(
                    "'inline' (default) renders inside the chat message; the user "
                    "can pop it out to the side panel or fullscreen. Use 'canvas' "
                    "only for a surface kept in view and updated while the "
                    "conversation continues, such as live progress or a dashboard."
                )
            ),
        ] = "inline",
        id: Annotated[
            Any,
            WithJsonSchema(_STRING_SCHEMA),
            Field(description="Alias for surface_id."),
        ] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Render a structured UI surface inline in chat or in the side panel canvas.

        `component` is one JSON object, never a string: {"type": "card",
        "children": [{"type": "text", "content": "Hi"}]}. Children are objects
        too. The A2UI schema is defined in suzent.a2ui.models. Use `content` for
        text components, `label` and `action` for buttons, and `columns` plus
        `rows` for tables. The `id` alias is accepted for compatibility with
        A2UISurface.

        For rich UI the typed components can't express (charts, SVG, custom
        dashboards, interactive prototypes), use the `html` component — a
        self-contained HTML document rendered in a sandboxed iframe. Its scripts
        run isolated from the host app. To send feedback back to the agent, the
        HTML posts a message to the host:
            window.parent.postMessage(
                {type: 'a2ui:action', action: 'my_action', context: {...}}, '*')
        which is delivered exactly like a button click or form submit.

        Lay surfaces out for a narrow column (roughly 360-700px wide): stack
        rather than spread wide, and let HTML size to its container instead of
        using fixed widths.
        """
        raw = _surface_payload(
            surface_id=surface_id,
            component=component,
            title=title,
            target=target,
            id=id,
            extra=kwargs,
        )
        try:
            raw["component"], was_string = coerce_component(raw.get("component"))
        except ComponentArgumentError as exc:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                f"Invalid A2UI surface. {exc}",
            )
        if was_string:
            logger.warning(
                "render_ui received `component` as a JSON string; accepted for "
                "compatibility but deprecated -- the schema declares an object."
            )

        if raw.get("component") is None:
            hint = ""
            stray = sorted(k for k in kwargs if k in _COMPONENT_FIELD_NAMES)
            if stray:
                hint = (
                    f" Found component fields at the top level ({', '.join(stray)}); "
                    "put them inside `component`."
                )
            return ToolResult.error_result(
                ToolErrorCode.MISSING_REQUIRED_PARAM,
                "Invalid A2UI surface. `component` is required and must be a JSON "
                'object such as {"type": "text", "content": "Hello"}.' + hint,
            )

        try:
            surface = _SURFACE_ADAPTER.validate_python(raw)
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_input=False)
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Invalid A2UI surface. Fix these and call render_ui again:\n"
                + _format_errors(errors),
                metadata={"errors": errors},
            )

        payload = surface.model_dump(exclude_none=True)
        sid = surface.id
        target_value = surface.target
        title_value = surface.title or sid
        payload["title"] = title_value
        # Orders re-renders of one surface id across turns, so the chat can
        # collapse the older copies, including ones reloaded from history.
        payload["rev"] = time.time_ns() // 1_000_000

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
