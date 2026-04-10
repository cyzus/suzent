"""
AskQuestionTool — ask the user one or more questions with optional selectable options.

Renders an inline A2UI surface so the user can click or fill in a form instead
of typing free-text replies. Prefer this over plain-text clarification questions.
"""

import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from suzent.tools.base import Tool, ToolGroup
from suzent.core.agent_deps import AgentDeps
from suzent.a2ui import pending as pending_questions


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:32].strip("_")


class QuestionItem(BaseModel):
    question: str = Field(description="The question text to display.")
    options: list[str] | None = Field(
        default=None,
        description="Selectable choices. Single question with options renders as buttons; "
        "multiple questions render as a form with select/checkbox fields.",
    )
    multi_select: bool = Field(
        default=False,
        description="Allow multiple selections. Renders one checkbox per option.",
    )
    allow_free_text: bool = Field(
        default=False,
        description="Add a text input alongside the option buttons/checkboxes.",
    )
    field_name: str = Field(
        default="",
        description="Key used in the response dict. Auto-slugged from question if omitted.",
    )
    required: bool = Field(default=False)


class AskQuestionTool(Tool):
    name = "AskQuestionTool"
    tool_name = "ask_question"
    group = ToolGroup.AGENT
    requires_approval = False

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        questions: list[QuestionItem],
        surface_id: str = Field(
            default="", description="Surface id; auto-generated if omitted."
        ),
    ) -> str:
        """Ask the user one or more questions as an interactive inline surface.

        Always prefer this over plain-text clarification. Bundle related questions
        into one call so the user answers everything at once.

        Callbacks:
            [canvas: choose_option] "<label>"              — single question with options
            [canvas: submit_question] {field: value, ...}  — form / multi-question
              single-select → string; multi_select → list[str]; free text → string
        """
        if not questions:
            return "Error: 'questions' list is empty."

        sid = surface_id or f"question_{_slug(questions[0].question)}"
        component = _build_component(questions)

        if ctx.deps.a2ui_queue is not None:
            future = pending_questions.create(ctx.deps.chat_id, sid)
            await ctx.deps.a2ui_queue.put(
                {
                    "event": "a2ui.render",
                    "id": sid,
                    "title": sid,
                    "component": component,
                    "target": "inline",
                    "deferred": True,
                }
            )
            answer = await asyncio.shield(future)
            return f"User answered: {json.dumps(answer, ensure_ascii=False)}"

        # Headless fallback
        lines = [
            f"- {q.question}" + (f" [{', '.join(q.options)}]" if q.options else "")
            for q in questions
        ]
        return "[Questions]\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Component builders
# ---------------------------------------------------------------------------


def _text(content: str, variant: str = "subheading") -> dict[str, Any]:
    return {"type": "text", "content": content, "variant": variant}


def _button(label: str, variant: str = "secondary") -> dict[str, Any]:
    return {
        "type": "button",
        "label": label,
        "action": "choose_option",
        "variant": variant,
    }


def _build_component(questions: list[QuestionItem]) -> dict[str, Any]:
    # Special case: single question with options, no multi_select → buttons (best UX)
    if len(questions) == 1 and questions[0].options and not questions[0].multi_select:
        q = questions[0]
        children: list[dict[str, Any]] = [_text(q.question)]
        for i, opt in enumerate(q.options):
            children.append(_button(opt, "primary" if i == 0 else "secondary"))

        # allow_free_text is handled inline in the select list on the frontend

        return {"type": "stack", "children": children}

    # General case: one form with all questions as fields
    fields: list[dict[str, Any]] = []
    for q in questions:
        name = q.field_name or _slug(q.question)
        options = q.options or []

        if options and q.multi_select:
            fields.append(
                {
                    "name": name,
                    "label": q.question,
                    "type": "multiselect",
                    "options": options,
                    "default": [],
                    "allow_free_text": q.allow_free_text,
                }
            )
        elif options:
            fields.append(
                {
                    "name": name,
                    "label": q.question,
                    "type": "select",
                    "options": options,
                    "required": q.required,
                    "allow_free_text": q.allow_free_text,
                }
            )
        else:
            fields.append(
                {
                    "name": name,
                    "label": q.question,
                    "type": "textarea",
                    "required": q.required,
                }
            )

    return {
        "type": "form",
        "action": "submit_question",
        "submit_label": "Submit",
        "fields": fields,
        "paged": True,
    }
