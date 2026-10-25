"""
AskQuestionTool — ask the user one or more questions with optional selectable options.

Renders an inline A2UI surface so the user can click or fill in a form instead
of typing free-text replies. Prefer this over plain-text clarification questions.
"""

import asyncio
import json
import re
import time
from contextlib import nullcontext
from typing import Any, Annotated

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
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
        description="Allow multiple selections. Renders one checkbox per option. "
        "A free-text 'other' choice is always added; don't list one yourself.",
    )
    field_name: str = Field(
        default="",
        description="Key used in the response dict. Auto-slugged from question if omitted.",
    )
    required: bool = Field(default=False)


class AskQuestionTool(Tool):
    name = "AskQuestionTool"
    tool_name = "ask_question"
    group = ToolGroup.INTERACTION
    builtin = True
    requires_approval = False
    session_guidance = (
        "Use AskQuestionTool for clarification, or genuine blockers after investigation, not as "
        "the first response to normal execution friction."
    )
    guidance_priority = 40

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        questions: Annotated[
            list[QuestionItem],
            Field(
                description="One or more questions to present to the user in a single interactive surface."
            ),
        ],
        surface_id: Annotated[
            str,
            Field(description="Stable surface id; auto-generated if omitted."),
        ] = "",
    ) -> ToolResult:
        """Ask the user one or more questions as an interactive inline surface.

        Always prefer this over plain-text clarification. Bundle related questions
        into one call so the user answers everything at once.

        Every question with options also offers a free-text "other" choice.

        Callback:
            [canvas: submit_question] {field: value, ...}
              single-select → string; multi_select → list[str]; free text → string
        """
        if not questions:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "'questions' list is empty.",
            )

        sid = surface_id or f"question_{_slug(questions[0].question)}"

        from suzent.core.focal_agent import is_focal_chat_id

        if (
            is_focal_chat_id(ctx.deps.chat_id)
            and ctx.deps.a2ui_queue is not None
            and not ctx.deps.social_context
        ):
            return await self._ask_without_waiting(ctx, sid, questions)

        component = _build_component(questions)

        # Sub-agents, scheduled runs and chat apps have no form to answer, so
        # waiting on one would hang the run.
        can_answer = (
            ctx.deps.interaction_profile == "interactive"
            and not ctx.deps.social_context
        )
        if can_answer and ctx.deps.a2ui_queue is not None:
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
            with ctx.deps.run_clock.paused() if ctx.deps.run_clock else nullcontext():
                answer = await asyncio.shield(future)
            return ToolResult.success_result(
                f"User answered: {json.dumps(answer, ensure_ascii=False)}",
                metadata={
                    "surface_id": sid,
                    "answer": answer,
                    "questions": [q.model_dump() for q in questions],
                },
            )

        # Headless fallback
        lines = [
            f"- {q.question}" + (f" [{', '.join(q.options)}]" if q.options else "")
            for q in questions
        ]
        return ToolResult.success_result(
            "Nobody can answer an interactive question in this run. "
            "Ask these in your reply instead, or continue with a stated assumption:\n"
            + "\n".join(lines),
            metadata={
                "surface_id": sid,
                "questions": [q.model_dump() for q in questions],
            },
        )

    @staticmethod
    async def _ask_without_waiting(
        ctx: RunContext[AgentDeps], sid: str, questions: list["QuestionItem"]
    ) -> ToolResult:
        """Show the form and end the turn instead of holding it open.

        Regent must stay free: a turn parked on an unanswered form would also
        hold back every wake-up and session report queued behind it. The form
        is an ordinary saved surface, so it is still there after a reload, and
        whenever the user submits it the answer arrives as their next message.
        Fields are named by their question so that message reads naturally.
        """
        await ctx.deps.a2ui_queue.put(
            {
                "event": "a2ui.render",
                "id": sid,
                "title": sid,
                "component": _build_component(questions, name_by_question=True),
                "target": "inline",
                "rev": time.time_ns() // 1_000_000,
            }
        )
        return ToolResult.success_result(
            "The question is shown to the user as a form in this conversation. "
            "They can answer whenever they like; the answer arrives as their next "
            "message. End your turn now with one short line pointing to the form, "
            "without repeating the questions.",
            metadata={
                "surface_id": sid,
                "waiting": False,
                "questions": [q.model_dump() for q in questions],
            },
        )


# ---------------------------------------------------------------------------
# Component builders
# ---------------------------------------------------------------------------


def _build_component(
    questions: list[QuestionItem], *, name_by_question: bool = False
) -> dict[str, Any]:
    # Always a form, even for one question: it is what carries the free-text
    # "other" choice and the number-key shortcuts.
    fields: list[dict[str, Any]] = []
    for q in questions:
        name = q.question if name_by_question else q.field_name or _slug(q.question)
        options = q.options or []

        if options and q.multi_select:
            fields.append(
                {
                    "name": name,
                    "label": q.question,
                    "type": "multiselect",
                    "options": options,
                    "default": [],
                    "allow_free_text": True,
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
                    "allow_free_text": True,
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
