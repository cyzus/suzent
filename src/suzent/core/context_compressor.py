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
from pydantic_ai.tools import RunContext

from suzent.core.agent_deps import AgentDeps

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.llm import LLMClient
from suzent.core.providers import get_effective_memory_config

logger = get_logger(__name__)

SUMMARY_PROMPT_TEMPLATE = """\
Your task is to create a detailed summary of the conversation below, paying close
attention to the user's explicit requests and the actions taken. This summary must
be thorough enough that development work can continue without losing context.

{steps_text}

Before writing the summary, wrap your reasoning in <analysis> tags: go through the
conversation chronologically and, for each part, identify the user's requests, the
approach taken, key decisions and code patterns, specific details (file names, full
code snippets, function signatures, edits), errors and how they were fixed, and any
explicit user feedback. Then double-check for technical accuracy and completeness.

After the analysis, write the summary inside <summary> tags using EXACTLY these
numbered sections (keep the headers verbatim):

## 1. Primary Request and Intent
All of the user's explicit requests and intents, in detail.

## 2. Key Technical Concepts
Important technical concepts, technologies, and frameworks discussed.

## 3. Files and Code Sections
Specific files and code sections examined, modified, or created. Include full code
snippets where applicable and a note on why each file/edit matters. Favor the most
recent messages.

## 4. Errors and Fixes
Errors encountered and how they were fixed, including any user feedback about them.

## 5. Problem Solving
Problems solved and any ongoing troubleshooting.

## 6. All User Messages
List ALL user messages that are not tool results, verbatim where short. These are
critical for tracking the user's evolving intent and feedback.

## 7. Pending Tasks
Pending tasks explicitly requested.

## 8. Current Work
Precisely what was being worked on immediately before this summary, with file names
and code snippets where applicable.

## 9. Next Step
The next step, only if directly in line with the user's most recent explicit request
and the work in progress. Include a direct verbatim quote from the most recent
messages showing where work left off. If the last task concluded, say so.

## 10. Exact Identifiers
Copy ALL of the following verbatim — never paraphrase or shorten:
UUIDs, file paths, URLs, API keys, IDs, hashes, hostnames, error codes.

Write in past tense. Discard verbose logs and resolved intermediate errors, but keep
code snippets and identifiers intact.

Structure your output as:
<analysis>
[your chronological analysis]
</analysis>
<summary>
[the numbered sections above]
</summary>
"""

# Per-part caps for rendering messages into summarizer input. Generous so code
# snippets / signatures / identifiers survive; only pathological outputs get clipped.
MSG_TEXT_TOOL_RESULT_LIMIT = 8000
MSG_TEXT_ASSISTANT_LIMIT = 8000
MSG_TEXT_TOOL_ARGS_LIMIT = 2000

# Header lines that must appear in the (post-strip) summary body. The retry loop and
# the chunk-merge validate against these.
REQUIRED_SECTIONS = [
    "## 1. Primary Request and Intent",
    "## 2. Key Technical Concepts",
    "## 3. Files and Code Sections",
    "## 4. Errors and Fixes",
    "## 5. Problem Solving",
    "## 6. All User Messages",
    "## 7. Pending Tasks",
    "## 8. Current Work",
    "## 9. Next Step",
    "## 10. Exact Identifiers",
]

# Stable markers identifying the synthetic summary messages injected into the
# LLM context after compaction. These exist only to fit the model's context
# window and must never surface in the user-facing display log.
COMPACTION_SUMMARY_REQUEST_MARKER = "[CONTEXT SUMMARY — READ BEFORE RESPONDING]"
COMPACTION_SUMMARY_RESPONSE_MARKER = "--- ARCHIVED CONTEXT SUMMARY ---"


def is_compaction_summary_text(text: Any) -> bool:
    """True if `text` is one of the synthetic compaction summary messages."""
    if not isinstance(text, str):
        return False
    return (
        COMPACTION_SUMMARY_REQUEST_MARKER in text
        or COMPACTION_SUMMARY_RESPONSE_MARKER in text
    )


def _fmt_tokens(tokens: int) -> str:
    return f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)


def extract_summary_body(raw: str) -> str:
    """Return the compaction summary with the <analysis> scratchpad removed.

    The prompt asks the model to draft in an <analysis> block (which improves the
    summary but carries no lasting value) and then write the real summary in a
    <summary> block. This strips the analysis and unwraps <summary>, tolerating a
    model that omits the tags (returns the cleaned text as-is).
    """
    if not raw:
        return ""
    import re

    text = re.sub(r"<analysis>[\s\S]*?</analysis>", "", raw, count=1)
    m = re.search(r"<summary>([\s\S]*?)</summary>", text)
    if m:
        return m.group(1).strip()
    # No <summary> tags — drop any stray tags and return the remainder.
    return re.sub(r"</?summary>", "", text).strip()


def build_post_compaction_usage(context_tokens: int) -> dict[str, Any]:
    """Build a context-window usage payload reflecting the post-compaction total.

    The frontend usage panel is normally fed by provider-reported usage from the
    last model request, which compaction never touches — so it stays stale until
    the next turn. Every compaction path emits this via ``emit_compaction_event``
    (stage="complete") so all surfaces update the same way. Cumulative/cache fields
    are reset; the next real request repopulates them.
    """
    return {
        "input_tokens": context_tokens,
        "output_tokens": 0,
        "total_tokens": context_tokens,
        "context_tokens": context_tokens,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "requests": 0,
        "details": {},
    }


def format_compaction_notice(
    *,
    stage: str,
    source: str,
    tokens_before: int = 0,
    tokens_after: Optional[int] = None,
    messages_before: Optional[int] = None,
    messages_after: Optional[int] = None,
    message: Optional[str] = None,
) -> str:
    prefix = "Auto context compaction" if source == "auto" else "Context compaction"

    if stage == "complete":
        token_summary = (
            f"{_fmt_tokens(tokens_before)} -> {_fmt_tokens(tokens_after)} tokens"
            if tokens_after is not None
            else "complete"
        )
        message_summary = (
            f" ({messages_before} -> {messages_after} messages)"
            if messages_before is not None and messages_after is not None
            else ""
        )
        return f"{prefix}: {token_summary}{message_summary}"

    if stage == "skipped":
        return f"{prefix} skipped: {message or 'nothing to compact'}"

    if stage == "error":
        return f"{prefix} failed: {message or 'unknown error'}"

    return f"{prefix}: {message or stage}"


def persist_compaction_notice(
    *,
    chat_id: str,
    stage: str,
    source: str,
    tokens_before: int = 0,
    tokens_after: Optional[int] = None,
    messages_before: Optional[int] = None,
    messages_after: Optional[int] = None,
    message: Optional[str] = None,
) -> str:
    notice = format_compaction_notice(
        stage=stage,
        source=source,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        messages_before=messages_before,
        messages_after=messages_after,
        message=message,
    )
    try:
        from suzent.database import get_database

        notice_message = {
            "role": "notice",
            "content": notice,
            "metadata": {
                "kind": "context_compaction",
                "source": source,
                "stage": stage,
            },
        }
        db = get_database()
        append_chat_message = getattr(db, "append_chat_message", None)
        if append_chat_message is not None:
            append_chat_message(chat_id, notice_message)
        else:
            chat = db.get_chat(chat_id)
            if chat is not None:
                messages = list(chat.messages or [])
                messages.append(notice_message)
                db.update_chat(chat_id, messages=messages)
    except Exception as e:
        logger.debug(f"Failed to persist compaction notice for {chat_id}: {e}")
    return notice


def build_compaction_event(
    *,
    stage: str,
    chat_id: str,
    messages_before: int,
    tokens_before: int,
    source: str = "auto",
    messages_after: Optional[int] = None,
    tokens_after: Optional[int] = None,
    message: Optional[str] = None,
) -> dict[str, Any]:
    """Build a normalized context compaction lifecycle event."""
    payload: dict[str, Any] = {
        "event": "auto_compaction",
        "stage": stage,
        "source": source,
        "chat_id": chat_id,
        "messages_before": messages_before,
        "tokens_before": tokens_before,
    }
    if messages_after is not None:
        payload["messages_after"] = messages_after
    if tokens_after is not None:
        payload["tokens_after"] = tokens_after
    if message is not None:
        payload["message"] = message
    return payload


def emit_compaction_event(
    *,
    chat_id: str,
    stage: str,
    source: str,
    messages_before: int = 0,
    tokens_before: int = 0,
    messages_after: Optional[int] = None,
    tokens_after: Optional[int] = None,
    message: Optional[str] = None,
    persist_result: bool = False,
) -> dict[str, Any]:
    payload = build_compaction_event(
        chat_id=chat_id,
        stage=stage,
        source=source,
        messages_before=messages_before,
        tokens_before=tokens_before,
        messages_after=messages_after,
        tokens_after=tokens_after,
        message=message,
    )

    # On completion, attach the recomputed context-window usage so every surface
    # (manual button, /compact slash, auto) refreshes the panel identically, and
    # persist it so a reload reflects the reduced context too.
    if stage == "complete" and tokens_after is not None:
        usage_data = build_post_compaction_usage(tokens_after)
        payload["usage"] = usage_data
        if chat_id:
            try:
                from suzent.database import get_database

                get_database().update_chat(chat_id, context_usage=usage_data)
            except Exception as e:
                logger.debug(
                    f"Failed to persist post-compaction usage for {chat_id}: {e}"
                )

    try:
        from suzent.core.stream_registry import emit_bus_event

        emit_bus_event(payload)
    except Exception as e:
        logger.debug(f"Failed to emit compaction event for {chat_id}: {e}")

    if persist_result and stage != "start":
        persist_compaction_notice(
            chat_id=chat_id,
            stage=stage,
            source=source,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_before=messages_before,
            messages_after=messages_after,
            message=message,
        )
    return payload


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
        source: str = "auto",
        messages_after: Optional[int] = None,
        tokens_after: Optional[int] = None,
        message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a normalized context compaction lifecycle event."""
        return build_compaction_event(
            stage=stage,
            source=source,
            chat_id=chat_id,
            messages_before=messages_before,
            messages_after=messages_after,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            message=message,
        )

    async def _perform_compression(
        self,
        messages: list,
        focus: Optional[str] = None,
        background_flush: bool = False,
    ) -> list:
        """
        Compress messages by summarizing older ones.

        Strategy:
        1. Keep the first message (system context).
        2. Pre-compaction flush: extract facts from messages about to be removed.
        3. Summarize the compressible middle block (chunked if large).
        4. Keep the most recent N messages intact.

        When ``background_flush`` is True the memory flush is scheduled as a
        fire-and-forget background task instead of awaited — used by the mid-run
        history processor so extraction never stalls an in-flight model request.
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
        if background_flush:
            self._schedule_pre_compaction_flush(messages_to_compress)
        else:
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
                        f"{COMPACTION_SUMMARY_REQUEST_MARKER}\n"
                        "The following is an authoritative summary of prior conversation history."
                    )
                )
            ]
        )
        summary_response = ModelResponse(
            parts=[
                TextPart(
                    content=(
                        f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\n"
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
        body = ""
        for attempt in range(3):
            full_prompt = prompt
            if missing_note:
                full_prompt += f"\n\nIMPORTANT: Your previous response was missing these sections: {missing_note}. Include ALL required sections inside the <summary> block."

            raw = await self.llm_client.complete(
                prompt=full_prompt,
                system="You are an expert technical summarizer.",
                temperature=0.3,
            )
            body = extract_summary_body(raw)

            if body and all(s in body for s in REQUIRED_SECTIONS):
                return body

            if body:
                missing = [s for s in REQUIRED_SECTIONS if s not in body]
                missing_note = ", ".join(missing)
                logger.warning(
                    f"Summary attempt {attempt + 1} missing sections: {missing_note}"
                )
            else:
                logger.warning(f"Summary attempt {attempt + 1} returned empty result")

        # Fall back to last non-empty body or empty string
        return body or ""

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
            return extract_summary_body(result)

        partial_summaries = await asyncio.gather(*[summarize_chunk(c) for c in chunks])
        combined = "\n\n---\n\n".join(s for s in partial_summaries if s)

        if not combined:
            return ""

        required_headers = "\n".join(REQUIRED_SECTIONS)
        merge_prompt = (
            "Merge these partial conversation summaries into a single coherent summary, "
            "preserving ALL of these sections (keep the headers verbatim):\n\n"
            f"{required_headers}\n\n"
            "Return only the merged summary — no <analysis> or <summary> tags.\n\n"
            f"{combined}"
        )
        merged = await self.llm_client.complete(
            prompt=merge_prompt,
            system="You are an expert technical summarizer.",
            temperature=0.3,
        )
        return extract_summary_body(merged) or combined

    def _schedule_pre_compaction_flush(self, messages_to_compress: list) -> None:
        """Run the pre-compaction memory flush as a fire-and-forget background task.

        Used from the mid-run history processor so heavy memory extraction never
        blocks the model request that triggered compaction. Snapshot the slice so a
        later mutation of the caller's list can't affect the deferred work.
        """
        snapshot = list(messages_to_compress)

        async def _flush() -> None:
            await self._pre_compaction_flush(snapshot)

        try:
            from suzent.core.task_registry import register_background_task
            import uuid as _uuid

            asyncio.ensure_future(
                register_background_task(
                    _flush(),
                    task_id=f"precompact_flush_{self.chat_id or 'nochat'}_{_uuid.uuid4().hex}",
                    description=f"Pre-compaction memory flush for chat {self.chat_id}",
                )
            )
        except Exception as e:
            logger.debug(f"Failed to schedule pre-compaction flush: {e}")

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
            logger.info(
                f"Pre-compaction flush: extracted {extracted_count} facts "
                f"from {len(messages_to_compress)} messages"
            )

        except Exception as e:
            logger.warning(f"Pre-compaction memory flush failed: {e}")

    def _messages_to_text(self, messages: list) -> str:
        """Convert pydantic-ai messages to text for summarization.

        Content is rendered close to verbatim so the summarizer can retain code
        snippets, function signatures, and identifiers (the old 500-char cap threw
        those away before the model ever saw them). Only very large parts are
        truncated, and generously, to bound pathological tool outputs.
        """

        def _clip(value: Any, limit: int, *, label: str = "") -> str:
            s = str(value or "")
            if len(s) <= limit:
                return s
            dropped = len(s) - limit
            note = f" [{dropped} chars truncated{f' from {label}' if label else ''}]"
            return s[:limit] + f"\n...{note}...\n"

        text = []
        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if hasattr(part, "content") and isinstance(part.content, str):
                        # User messages are short and critical to intent — keep whole.
                        text.append(f"User: {part.content}")
                    if isinstance(part, ToolReturnPart):
                        output = _clip(
                            part.content,
                            MSG_TEXT_TOOL_RESULT_LIMIT,
                            label="tool result",
                        )
                        text.append(f"Tool Result ({part.tool_name}): {output}")
            elif isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, TextPart):
                        text.append(
                            f"Assistant: {_clip(part.content, MSG_TEXT_ASSISTANT_LIMIT)}"
                        )
                    elif isinstance(part, ToolCallPart):
                        args_str = (
                            _clip(part.args, MSG_TEXT_TOOL_ARGS_LIMIT)
                            if part.args
                            else ""
                        )
                        text.append(f"Action: {part.tool_name}({args_str})")
        return "\n".join(text)


# ---------------------------------------------------------------------------
# Mid-run compaction — pydantic-ai history processor
# ---------------------------------------------------------------------------


def _message_has_compaction_marker(msg: Any) -> bool:
    """True if a pydantic-ai message is one of the synthetic summary messages."""
    for part in getattr(msg, "parts", []) or []:
        if is_compaction_summary_text(getattr(part, "content", None)):
            return True
    return False


def context_input_tokens(ctx: Any, messages: list) -> int:
    """Best-effort current context size for a run.

    Prefers the provider-reported prompt size from the previous request in this
    run (``ctx.usage.input_tokens``) — the ground truth for what the next request
    will cost — and falls back to the char-based estimate on the first request
    (before any usage is available).
    """
    try:
        usage = getattr(ctx, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        if input_tokens > 0:
            return input_tokens
    except Exception:
        pass
    return estimate_tokens(messages, CONFIG.max_context_tokens).estimated_tokens


def make_compaction_history_processor(source: str = "auto_midrun"):
    """Build a pydantic-ai history processor that compacts context mid-run.

    Registered via ``Agent(history_processors=[...])``, it runs before EVERY model
    request within a run — so a tool-heavy turn that grows past the trigger
    threshold gets compacted in-flight instead of only at turn boundaries.

    The processor only rewrites what is SENT to the model (first message + a
    synthetic summary pair + the recent tail, using the existing
    ``COMPACTION_SUMMARY_*`` markers). Turn-end persistence reads the agent's
    resulting ``last_messages``, so the compacted history is what gets snapshotted.
    """

    async def _processor(ctx: RunContext[AgentDeps], messages: list) -> list:
        if not messages:
            return messages

        deps = getattr(ctx, "deps", None)
        # Stateless/system chats (dream, sub-agents) run a fixed self-contained
        # prompt and must never be compacted.
        if getattr(deps, "stateless", False):
            return messages

        limit = CONFIG.max_context_tokens
        trigger = limit * CONFIG.context_compaction_trigger
        current_tokens = context_input_tokens(ctx, messages)
        if current_tokens < trigger:
            return messages

        # Idempotency: if the tail is already summary-framed and we're only just
        # over the line because of the recent turns, another pass can't help.
        keep_recent = CONFIG.compaction_keep_recent_turns * 2
        if len(messages) <= keep_recent + 1:
            return messages
        already_compacted = any(_message_has_compaction_marker(m) for m in messages)

        chat_id = getattr(deps, "chat_id", "") or ""
        user_id = getattr(deps, "user_id", None)

        messages_before = len(messages)
        tokens_before = current_tokens
        emit_compaction_event(
            chat_id=chat_id,
            stage="start",
            source=source,
            messages_before=messages_before,
            tokens_before=tokens_before,
        )

        compressor = ContextCompressor(chat_id=chat_id, user_id=user_id)
        try:
            compressed = await asyncio.wait_for(
                compressor._perform_compression(messages, background_flush=True),
                timeout=CONFIG.compaction_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Mid-run compaction timed out, falling back to hard trim")
            compressed = messages[:1] + messages[-keep_recent:]
        except Exception as e:
            logger.error(f"Mid-run compaction failed: {e}")
            emit_compaction_event(
                chat_id=chat_id,
                stage="error",
                source=source,
                messages_before=messages_before,
                tokens_before=tokens_before,
                message=str(e),
            )
            return messages

        # pydantic-ai requires the processed history to be non-empty and to end
        # with a ModelRequest. If compaction would violate that (edge cases in the
        # tail slice), skip rather than crash the run.
        if not compressed or not isinstance(compressed[-1], ModelRequest):
            logger.debug(
                "Mid-run compaction produced an invalid tail; skipping this pass"
            )
            emit_compaction_event(
                chat_id=chat_id,
                stage="skipped",
                source=source,
                messages_before=messages_before,
                messages_after=len(messages),
                tokens_before=tokens_before,
            )
            return messages

        if len(compressed) >= len(messages):
            # No reduction (e.g. already compacted and nothing else to drop).
            if not already_compacted:
                emit_compaction_event(
                    chat_id=chat_id,
                    stage="skipped",
                    source=source,
                    messages_before=messages_before,
                    messages_after=len(compressed),
                    tokens_before=tokens_before,
                )
            return compressed

        tokens_after = estimate_tokens(compressed, limit).estimated_tokens
        emit_compaction_event(
            chat_id=chat_id,
            stage="complete",
            source=source,
            messages_before=messages_before,
            messages_after=len(compressed),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
        )
        logger.info(
            f"Mid-run compaction: {messages_before} -> {len(compressed)} messages "
            f"(~{tokens_before} -> ~{tokens_after} tokens)"
        )
        return compressed

    return _processor
