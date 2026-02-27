"""
Context Compressor: Manages conversation history by trimming and summarizing.

Works with pydantic-ai's message history format (list of ModelMessage objects).
Supports pre-compaction memory flush: before trimming messages, extract
important facts and persist them to the memory system.
"""

from typing import List, Optional

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    TextPart,
)

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.llm import LLMClient
from suzent.core.provider_factory import get_effective_memory_config

logger = get_logger(__name__)

SUMMARY_PROMPT_TEMPLATE = """
You are a helpful assistant summarizing the conversation history for an AI agent to free up context window space.

Here is a segment of the conversation history (actions taken, thoughts, and outputs):
--------------------------------------------------
{steps_text}
--------------------------------------------------

Please provide a concise but comprehensive summary of these events.
- Focus on key decisions, tool outputs, and facts learned.
- Discard verbose logs or intermediate errors that are resolved.
- Structure it as a "Previous Context Summary" that the agent can read to understand what happened.
- Write it in the past tense.
"""


class ContextCompressor:
    """Handles compression of pydantic-ai message history.

    Operates on a list of ModelMessage objects (from result.all_messages()).
    Supports pre-compaction memory flush before trimming.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        if llm_client:
            self.llm_client = llm_client
        else:
            config = get_effective_memory_config()
            self.llm_client = LLMClient(model=config["extraction_model"])

        self.max_history_messages = CONFIG.max_history_steps * 2  # request+response pairs
        self.chat_id = chat_id
        self.user_id = user_id

    async def compress_messages(self, messages: list) -> list:
        """
        Check if message history needs compression and perform it if necessary.

        Args:
            messages: List of pydantic-ai ModelMessage objects.

        Returns:
            The (possibly trimmed) message list.
        """
        if not messages:
            return messages

        if len(messages) <= self.max_history_messages:
            return messages

        logger.info(
            f"Compressing message history: {len(messages)} messages "
            f"exceeds limit of {self.max_history_messages}"
        )

        try:
            return await self._perform_compression(messages)
        except Exception as e:
            logger.error(f"Context compression failed: {e}")
            return messages

    async def _perform_compression(self, messages: list) -> list:
        """
        Compress messages by summarizing older ones.

        Strategy:
        1. Keep the first message (system context).
        2. Pre-compaction flush: extract facts from messages about to be removed.
        3. Summarize the compressible middle block.
        4. Keep the most recent N messages intact.
        """
        # Keep last N messages (at least 10, or 25% of max)
        keep_recent = max(10, int(self.max_history_messages * 0.25))

        if len(messages) <= keep_recent + 1:
            return messages

        start_index = 1  # After first system/context message
        end_index = len(messages) - keep_recent

        if start_index >= end_index:
            return messages

        messages_to_compress = messages[start_index:end_index]

        # Pre-compaction memory flush
        await self._pre_compaction_flush(messages_to_compress)

        # Generate summary
        steps_text = self._messages_to_text(messages_to_compress)
        summary = await self.llm_client.complete(
            prompt=SUMMARY_PROMPT_TEMPLATE.format(steps_text=steps_text),
            system="You are an expert technical summarizer.",
            temperature=0.3,
        )

        if not summary:
            logger.warning("Failed to generate summary for compression.")
            # Fallback: just trim without summary
            return messages[:1] + messages[end_index:]

        # Create a synthetic summary message
        from pydantic_ai.messages import (
            ModelRequest,
            UserPromptPart,
            ModelResponse,
            TextPart as ResponseTextPart,
        )

        summary_request = ModelRequest(parts=[
            UserPromptPart(content="[System: What happened in the previous conversation?]")
        ])
        summary_response = ModelResponse(parts=[
            ResponseTextPart(content=(
                f"--- ARCHIVED CONTEXT SUMMARY ---\n{summary}\n--- END ARCHIVED CONTEXT ---"
            ))
        ])

        # Rebuild: [first msg] + [summary pair] + [recent messages]
        new_messages = messages[:1] + [summary_request, summary_response] + messages[end_index:]

        logger.info(
            f"Message history compressed: {len(messages)} → {len(new_messages)} messages"
        )
        return new_messages

    async def _pre_compaction_flush(self, messages_to_compress: list) -> None:
        """
        Extract memories from messages about to be compressed away.
        """
        if not CONFIG.memory_enabled:
            return
        if not self.chat_id or not self.user_id:
            return

        try:
            from suzent.memory.lifecycle import get_memory_manager
            from suzent.memory import ConversationTurn, Message, AgentAction

            memory_mgr = get_memory_manager()
            if not memory_mgr:
                return

            # Extract content from messages
            user_parts = []
            assistant_parts = []
            actions = []

            for msg in messages_to_compress:
                if isinstance(msg, ModelRequest):
                    for part in msg.parts:
                        if hasattr(part, "content") and isinstance(part.content, str):
                            user_parts.append(part.content)
                        if isinstance(part, ToolReturnPart):
                            actions.append(
                                AgentAction(
                                    tool=part.tool_name,
                                    args={},
                                    output=str(part.content)[:200],
                                )
                            )
                elif isinstance(msg, ModelResponse):
                    for part in msg.parts:
                        if isinstance(part, TextPart):
                            text = part.content
                            if len(text) > 300:
                                text = text[:300] + "..."
                            assistant_parts.append(text)
                        elif isinstance(part, ToolCallPart):
                            actions.append(
                                AgentAction(
                                    tool=part.tool_name,
                                    args=part.args if isinstance(part.args, dict) else {},
                                )
                            )

            user_text = "\n".join(p for p in user_parts if p).strip()
            assistant_text = "\n".join(p for p in assistant_parts if p).strip()

            if not user_text and not assistant_text:
                return

            turn = ConversationTurn(
                user_message=Message(
                    role="user",
                    content=user_text or "(context from previous messages)",
                ),
                assistant_message=Message(
                    role="assistant",
                    content=assistant_text or "(actions taken in previous messages)",
                ),
                agent_actions=actions[:10],
            )

            result = await memory_mgr.process_conversation_turn_for_memories(
                conversation_turn=turn,
                chat_id=self.chat_id,
                user_id=self.user_id,
            )

            extracted_count = len(result.extracted_facts) if result else 0
            created_count = len(result.memories_created) if result else 0
            logger.info(
                f"Pre-compaction flush: extracted {extracted_count} facts, "
                f"created {created_count} memories from {len(messages_to_compress)} messages"
            )

        except Exception as e:
            logger.warning(f"Pre-compaction memory flush failed: {e}")

    def _messages_to_text(self, messages: list) -> str:
        """Convert pydantic-ai messages to text for summarization."""
        text = []
        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if hasattr(part, "content") and isinstance(part.content, str):
                        text.append(f"User: {part.content[:500]}")
                    if isinstance(part, ToolReturnPart):
                        output = str(part.content)[:500]
                        text.append(f"Tool Result ({part.tool_name}): {output}")
            elif isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        text.append(f"Assistant: {part.content[:500]}")
                    elif isinstance(part, ToolCallPart):
                        args_str = str(part.args)[:200] if part.args else ""
                        text.append(f"Action: {part.tool_name}({args_str})")
        return "\n".join(text)
