"""In-conversation delivery, persisted and replayed through ordinary tool results."""

from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelRequest, UserPromptPart

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolResult

Reaction = Literal["👍", "❤️", "👀", "✅", "🎉", "😂", "🤔", "🙏", ""]


class FocalMessageTool(Tool):
    """Send one or several separate chat bubbles to the user here, then keep working."""

    name = "FocalMessageTool"
    tool_name = "send_message"
    display_name = "Send a message"
    group = ""
    deferrable = False
    session_guidance = (
        "Talk naturally with the user. Use send_message for a short message now "
        "while you continue working, or a few separate bubbles when they help. "
        "Messages are delivered immediately in this conversation, not externally. "
        "Do not repeat sent messages in your final answer. Prefer sending intermediate "
        "messages here and returning your last message normally. If everything has "
        "already been said, an empty final response is fine. Do not split every "
        "sentence or send filler acknowledgements. Use react_to_message sparingly "
        "to acknowledge the current user message; a reaction can be enough on its own. "
        "Never send messages and then claim HEARTBEAT_OK: sent messages are visible."
    )

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        messages: Annotated[list[str], Field(min_length=1, max_length=4)],
    ) -> ToolResult:
        from suzent.core.focal_agent import FOCAL_CHAT_ID

        if ctx.deps.chat_id != FOCAL_CHAT_ID:
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED, "Only Regent can send messages here."
            )
        texts = [text.strip() for text in messages]
        if not 1 <= len(texts) <= 4 or any(
            not text or len(text) > 4000 for text in texts
        ):
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Send 1–4 non-empty messages, each at most 4000 characters.",
            )
        return ToolResult.success_result(
            "Delivered. Do not repeat these messages in your final answer.",
            metadata={"regent_messages": texts},
        )


class FocalReactionTool(Tool):
    """React to the user message that started this turn. Empty emoji removes the reaction."""

    name = "FocalReactionTool"
    tool_name = "react_to_message"
    display_name = "React to a message"
    group = ""
    deferrable = False

    async def forward(self, ctx: RunContext[AgentDeps], emoji: Reaction) -> ToolResult:
        from suzent.core.focal_agent import FOCAL_CHAT_ID
        from suzent.core.system_reminder import strip_system_reminders

        if ctx.deps.chat_id != FOCAL_CHAT_ID:
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED, "Only Regent can react here."
            )
        if emoji not in ("👍", "❤️", "👀", "✅", "🎉", "😂", "🤔", "🙏", ""):
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "Unsupported reaction."
            )
        prompt = next(
            (
                part
                for message in reversed(ctx.messages)
                if isinstance(message, ModelRequest)
                for part in reversed(message.parts)
                if isinstance(part, UserPromptPart)
            ),
            None,
        )
        content = prompt.content if prompt else ""
        human_input = (
            bool(strip_system_reminders(content).strip())
            if isinstance(content, str)
            else bool(content)
        )
        if not human_input:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "There is no user message in this turn to react to.",
            )
        return ToolResult.success_result(
            "Reaction updated.", metadata={"regent_reaction": emoji}
        )
