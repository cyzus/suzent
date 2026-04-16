"""
Context Compressor: Manages conversation history by trimming and summarizing.

Works with pydantic-ai's message history format (list of ModelMessage objects).
Supports pre-compaction memory flush: before trimming messages, extract
important facts and persist them to the memory system.
"""

import asyncio
import dataclasses
from dataclasses import dataclass
from typing import Optional, Any

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
from suzent.core.providers import get_effective_memory_config

logger = get_logger(__name__)

SUMMARY_PROMPT_TEMPLATE = """
You are summarizing conversation history to free up context window space.

{steps_text}

Provide a concise but complete summary using EXACTLY these sections:

## Key Decisions
List decisions made and their rationale.

## Open Tasks
List in-progress, blocked, or pending tasks with their current state.

## Important Facts
Key facts, outputs, and results learned during the conversation.

## Exact Identifiers
Copy ALL of the following verbatim — never paraphrase or shorten:
UUIDs, file paths, URLs, API keys, IDs, hashes, hostnames, error codes.

Write in past tense. Discard verbose logs and resolved intermediate errors.
"""

REQUIRED_SECTIONS = [
    "## Key Decisions",
    "## Open Tasks",
    "## Important Facts",
    "## Exact Identifiers",
]


# ---------------------------------------------------------------------------
# Phase 1 — Token Engine
# ---------------------------------------------------------------------------


@dataclass
class TokenBudget:
    estimated_tokens: int
    limit: int
    trigger_threshold: float = 0.80
    soft_trim_threshold: float = 0.60
    hard_trim_threshold: float = 0.80

    @property
    def over_soft(self) -> bool:
        return self.estimated_tokens >= self.limit * self.soft_trim_threshold

    @property
    def over_hard(self) -> bool:
        return self.estimated_tokens >= self.limit * self.hard_trim_threshold

    @property
    def over_trigger(self) -> bool:
        return self.estimated_tokens >= self.limit * self.trigger_threshold


def estimate_tokens(messages: list, limit: int) -> TokenBudget:
    """Estimate token count using ~4 chars/token heuristic."""
    total_chars = sum(
        len(str(getattr(part, "content", "") or ""))
        for msg in messages
        for part in getattr(msg, "parts", [])
    )
    return TokenBudget(
        estimated_tokens=total_chars // 4,
        limit=limit,
        trigger_threshold=CONFIG.context_compaction_trigger,
        soft_trim_threshold=CONFIG.context_soft_trim_threshold,
        hard_trim_threshold=CONFIG.context_hard_trim_threshold,
    )


# ---------------------------------------------------------------------------
# Phase 2 — Multi-Layer Tool Result Trimming
# ---------------------------------------------------------------------------


class ToolResultTrimmer:
    SOFT_HEAD = 1000
    SOFT_TAIL = 500
    HARD_PLACEHOLDER = "[Tool output cleared to free context space]"

    @classmethod
    def apply_soft_trim(cls, messages: list, budget: TokenBudget) -> list:
        """Truncate large ToolReturnPart content to head + tail for older messages."""
        keep_recent = CONFIG.compaction_keep_recent_turns * 2
        cutoff = max(0, len(messages) - keep_recent)
        result = []
        for i, msg in enumerate(messages):
            if i >= cutoff or not isinstance(msg, ModelRequest):
                result.append(msg)
                continue
            new_parts = []
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    content = str(part.content or "")
                    if len(content) > cls.SOFT_HEAD + cls.SOFT_TAIL + 20:
                        trimmed = (
                            content[: cls.SOFT_HEAD]
                            + f"\n... [{len(content) - cls.SOFT_HEAD - cls.SOFT_TAIL} chars trimmed] ...\n"
                            + content[-cls.SOFT_TAIL :]
                        )
                        part = dataclasses.replace(part, content=trimmed)
                new_parts.append(part)
            result.append(dataclasses.replace(msg, parts=new_parts))
        return result

    @classmethod
    def apply_hard_clear(cls, messages: list, budget: TokenBudget) -> list:
        """Replace ToolReturnPart content with placeholder for oldest messages."""
        keep_recent = CONFIG.compaction_keep_recent_turns * 2
        cutoff = max(0, len(messages) - keep_recent)
        result = []
        for i, msg in enumerate(messages):
            if i >= cutoff or not isinstance(msg, ModelRequest):
                result.append(msg)
                continue
            new_parts = []
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    content = str(part.content or "")
                    if len(content) > 200:
                        part = dataclasses.replace(part, content=cls.HARD_PLACEHOLDER)
                new_parts.append(part)
            result.append(dataclasses.replace(msg, parts=new_parts))
        return result


# ---------------------------------------------------------------------------
# Main compressor
# ---------------------------------------------------------------------------


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

        self.chat_id = chat_id
        self.user_id = user_id

    async def compress_messages(self, messages: list) -> list:
        """Check if message history needs compression and perform it if necessary."""
        if not messages:
            return messages

        budget = estimate_tokens(messages, CONFIG.max_context_tokens)
        if not budget.over_trigger:
            return messages

        logger.info(
            f"Compressing message history: ~{budget.estimated_tokens} tokens "
            f"exceeds trigger threshold ({budget.trigger_threshold:.0%} of {budget.limit})"
        )

        try:
            return await asyncio.wait_for(
                self._perform_compression(messages),
                timeout=CONFIG.compaction_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Compaction timed out, falling back to hard trim")
            keep = CONFIG.compaction_keep_recent_turns * 2
            return messages[:1] + messages[-keep:]
        except Exception as e:
            logger.error(f"Context compression failed: {e}")
            return messages

    def get_auto_compaction_plan(self, messages: list) -> dict[str, Any]:
        """Compute whether an automatic compaction attempt should be made."""
        budget = estimate_tokens(messages, CONFIG.max_context_tokens)
        keep_recent = CONFIG.compaction_keep_recent_turns * 2
        can_attempt = budget.over_trigger and len(messages) > keep_recent + 1
        return {
            "can_attempt": can_attempt,
            "messages_before": len(messages),
            "tokens_before": budget.estimated_tokens,
        }

    def build_auto_compaction_event(
        self,
        *,
        stage: str,
        chat_id: str,
        messages_before: int,
        tokens_before: int,
        messages_after: Optional[int] = None,
        tokens_after: Optional[int] = None,
    ) -> dict[str, Any]:
        """Build a normalized event-bus payload for auto compaction lifecycle updates."""
        payload: dict[str, Any] = {
            "event": "auto_compaction",
            "stage": stage,
            "chat_id": chat_id,
            "messages_before": messages_before,
            "tokens_before": tokens_before,
        }
        if messages_after is not None:
            payload["messages_after"] = messages_after
        if tokens_after is not None:
            payload["tokens_after"] = tokens_after
        return payload

    async def _perform_compression(
        self, messages: list, focus: Optional[str] = None
    ) -> list:
        """
        Compress messages by summarizing older ones.

        Strategy:
        1. Keep the first message (system context).
        2. Pre-compaction flush: extract facts from messages about to be removed.
        3. Summarize the compressible middle block (chunked if large).
        4. Keep the most recent N messages intact.
        """
        keep_recent = CONFIG.compaction_keep_recent_turns * 2

        if len(messages) <= keep_recent + 1:
            return messages

        start_index = 1  # After first system/context message
        end_index = len(messages) - keep_recent

        if start_index >= end_index:
            return messages

        messages_to_compress = messages[start_index:end_index]

        # Pre-compaction memory flush
        await self._pre_compaction_flush(messages_to_compress)

        # Adaptive chunk size
        budget = estimate_tokens(messages, CONFIG.max_context_tokens)
        chunk_size = CONFIG.compaction_chunk_size
        if len(messages_to_compress) > 0:
            avg_tokens = budget.estimated_tokens / len(messages)
            if avg_tokens > 2000:
                chunk_size = chunk_size // 2

        # Chunked or single-pass summarization
        if len(messages_to_compress) > chunk_size:
            summary = await self._chunked_summarize(
                messages_to_compress, chunk_size, focus
            )
        else:
            summary = await self._summarize_with_retry(messages_to_compress, focus)

        if not summary:
            logger.warning("Failed to generate summary for compression.")
            return messages[:1] + messages[end_index:]

        # Phase 6 — improved synthetic summary framing
        from pydantic_ai.messages import UserPromptPart

        summary_request = ModelRequest(
            parts=[
                UserPromptPart(
                    content=(
                        "[CONTEXT SUMMARY — READ BEFORE RESPONDING]\n"
                        "The following is an authoritative summary of prior conversation history."
                    )
                )
            ]
        )
        summary_response = ModelResponse(
            parts=[
                TextPart(
                    content=(
                        "--- ARCHIVED CONTEXT SUMMARY ---\n"
                        f"{summary}\n"
                        "---\n"
                        "This summary supersedes any earlier tool outputs or conversation fragments "
                        "that are no longer in your context window.\n"
                        "--- END ARCHIVED CONTEXT ---"
                    )
                )
            ]
        )

        new_messages = (
            messages[:1] + [summary_request, summary_response] + messages[end_index:]
        )

        logger.info(
            f"Message history compressed: {len(messages)} → {len(new_messages)} messages"
        )
        return new_messages

    async def _summarize_with_retry(
        self, messages: list, focus: Optional[str] = None
    ) -> str:
        """Summarize with up to 3 attempts, validating required sections."""
        steps_text = self._messages_to_text(messages)
        prompt = SUMMARY_PROMPT_TEMPLATE.format(steps_text=steps_text)
        if focus:
            prompt += f"\n\nAdditional focus: {focus}"

        missing_note = ""
        for attempt in range(3):
            full_prompt = prompt
            if missing_note:
                full_prompt += f"\n\nIMPORTANT: Your previous response was missing these sections: {missing_note}. Include ALL four required sections."

            summary = await self.llm_client.complete(
                prompt=full_prompt,
                system="You are an expert technical summarizer.",
                temperature=0.3,
            )

            if summary and all(s in summary for s in REQUIRED_SECTIONS):
                return summary

            if summary:
                missing = [s for s in REQUIRED_SECTIONS if s not in summary]
                missing_note = ", ".join(missing)
                logger.warning(
                    f"Summary attempt {attempt + 1} missing sections: {missing_note}"
                )
            else:
                logger.warning(f"Summary attempt {attempt + 1} returned empty result")

        # Fall back to last non-empty result or empty string
        return summary or ""

    async def _chunked_summarize(
        self, messages: list, chunk_size: int, focus: Optional[str] = None
    ) -> str:
        """Split into chunks, summarize in parallel, then merge."""
        chunks = [
            messages[i : i + chunk_size] for i in range(0, len(messages), chunk_size)
        ]

        async def summarize_chunk(chunk: list) -> str:
            steps_text = self._messages_to_text(chunk)
            prompt = SUMMARY_PROMPT_TEMPLATE.format(steps_text=steps_text)
            if focus:
                prompt += f"\n\nAdditional focus: {focus}"
            result = await self.llm_client.complete(
                prompt=prompt,
                system="You are an expert technical summarizer.",
                temperature=0.3,
            )
            return result or ""

        partial_summaries = await asyncio.gather(*[summarize_chunk(c) for c in chunks])
        combined = "\n\n---\n\n".join(s for s in partial_summaries if s)

        if not combined:
            return ""

        merge_prompt = (
            "Merge these partial conversation summaries into a single coherent summary, "
            "preserving ALL four required sections:\n\n"
            "## Key Decisions\n## Open Tasks\n## Important Facts\n## Exact Identifiers\n\n"
            f"{combined}"
        )
        merged = await self.llm_client.complete(
            prompt=merge_prompt,
            system="You are an expert technical summarizer.",
            temperature=0.3,
        )
        return merged or combined

    async def _pre_compaction_flush(self, messages_to_compress: list) -> None:
        """Extract memories from messages about to be compressed away."""
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
                                    args=part.args
                                    if isinstance(part.args, dict)
                                    else {},
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
