"""
RenderUITool — push structured A2UI surfaces to the frontend canvas.

Agents call render_ui() to display rich interactive components (tables, forms,
cards, buttons) in the canvas panel alongside the chat. The same surface_id
performs an upsert: calling again with the same id replaces the existing surface.
"""

import json
from typing import Any

from pydantic_ai import RunContext

from suzent.tools.base import Tool
from suzent.core.agent_deps import AgentDeps


class RenderUITool(Tool):
    name = "RenderUITool"
    tool_name = "render_ui"
    requires_approval = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        surface_id: str,
        component: dict[str, Any],
        title: str = "",
        target: str = "canvas",
    ) -> str:
        """Render a structured UI surface in the canvas panel or inline in chat.

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

        Interactions are returned as: [canvas: <action>] "<button_label>"
        Always set "action" on buttons/forms. Use inline buttons to ask the user
        to choose between options instead of plain text questions.
        For full reference and examples, call: skill_execute("canvas")
        """
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
            return f"Surface '{surface_id}' rendered {location}."

        # Fallback: if no queue (e.g. CLI/headless), return JSON summary
        preview = json.dumps(component, indent=2)[:300]
        return f"[Canvas not available] Surface '{surface_id}':\n{preview}"
