"""
Context Compressor: Manages conversation history by trimming and summarizing.

Works with pydantic-ai's message history format (list of ModelMessage objects).
Supports pre-compaction memory flush: before trimming messages, extract
important facts and persist them to the memory system.
"""

import asyncio
import contextlib
import dataclasses
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    TextContent,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.tools import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.core.context_usage import estimate_text
from suzent.core.message_history import safe_tool_history_tail_start

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.llm import LLMClient
from suzent.core.providers import get_effective_memory_config

logger = get_logger(__name__)


class CompactionError(RuntimeError):
    """A summary could not safely replace the original model history."""


SUMMARY_PROMPT_TEMPLATE = """\
Your task is to create a detailed summary of the conversation below, paying close
attention to the user's explicit requests and the actions taken. This summary must
be thorough enough that development work can continue without losing context.

{steps_text}

Return only a <summary> block, without analysis or a preamble, using EXACTLY these
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

SUMMARY_MAX_TOKENS = 8192


def _user_prompt_text(part: UserPromptPart) -> str:
    content = part.content
    if isinstance(content, str):
        return content
    return "\n".join(
        item if isinstance(item, str) else item.content
        for item in content
        if isinstance(item, (str, TextContent))
    )


def _latest_user_prompt(messages: list) -> str:
    """Keep the active request explicit when a long tool run outgrows the tail."""
    for message in reversed(messages[1:]):
        if not isinstance(message, ModelRequest):
            continue
        for part in reversed(message.parts):
            if isinstance(part, UserPromptPart):
                content = _user_prompt_text(part)
                if is_compaction_summary_text(content):
                    continue
                from suzent.core.system_reminder import strip_system_reminders

                text = strip_system_reminders(content).strip()
                if text:
                    return text
    anchor = "## Active user request (verbatim)\n"
    for message in reversed(messages):
        if not isinstance(message, ModelResponse):
            continue
        for part in reversed(message.parts):
            content = getattr(part, "content", None)
            if isinstance(content, str) and anchor in content:
                return content.split(anchor, 1)[1].split("\n---\n", 1)[0].strip()
    return ""


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


def build_summary_pair(summary: str, messages: list) -> list:
    """The synthetic request/response pair that stands in for compacted history.

    It carries the user's current request verbatim, because the message kept
    ahead of it is the chat's *first* request: after a long tool run the current
    one is no longer in the tail, and the agent went back to that first request
    as if it were still the task.
    """
    from suzent.core.system_reminder import (
        make_user_prompt_part,
        sanitize_untrusted_text,
    )

    # The summary is model output derived from tool content an attacker may
    # control, so it can be steered into emitting literal reminder
    # delimiters — including by reassembling them from an escaped form. It is
    # inserted after the sanitizing history processor has run and lands in
    # persisted history, so it is neutralized here at the point of creation.
    body = sanitize_untrusted_text(summary)
    active_request = _latest_user_prompt(messages)
    if active_request:
        # The request stays last in the section: a later pass reads it back out
        # of this summary once the original message has been compacted away.
        body += (
            "\n\nThe first message of the conversation is where the chat began and "
            "may be an earlier task that is already finished. The request below "
            "is what the user currently wants; continue it."
            "\n\n## Active user request (verbatim)\n"
            + sanitize_untrusted_text(active_request)
        )
    return [
        ModelRequest(
            parts=[
                make_user_prompt_part(
                    f"{COMPACTION_SUMMARY_REQUEST_MARKER}\n"
                    "The following is an authoritative summary of prior conversation history."
                )
            ]
        ),
        ModelResponse(
            parts=[
                TextPart(
                    content=(
                        f"{COMPACTION_SUMMARY_RESPONSE_MARKER}\n"
                        f"{body}\n"
                        "---\n"
                        "This summary supersedes any earlier tool outputs or conversation fragments "
                        "that are no longer in your context window.\n"
                        "--- END ARCHIVED CONTEXT ---"
                    )
                )
            ]
        ),
    ]


def _fmt_tokens(tokens: int) -> str:
    return f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)


def extract_summary_body(raw: str) -> str:
    """Return the compaction summary with the <analysis> scratchpad removed.

    Older prompts requested an analysis block. Strip that legacy wrapper and
    unwrap the summary, tolerating responses that omit the tags.
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


# Budget used when the active model is unknown or absent from the capability
# registry. Deliberately conservative: overshooting a model's real window costs a
# hard provider error mid-turn, while undershooting only compacts a little early.
DEFAULT_CONTEXT_LIMIT_TOKENS = 200_000


def resolve_context_limit(model_id: Optional[str] = None) -> int:
    """Context budget for the model actually running this conversation.

    The trigger used to be a single fixed number for every model, which is wrong
    in both directions: a 1M-token model got compacted at a fraction of its
    window, and a 128k model sailed past its real limit until the provider
    rejected the request outright.

    ``CONFIG.max_context_tokens`` keeps working as an explicit *ceiling* (a user
    who wants to cap cost or latency below what the model allows), and 0 — the
    default — means "whatever the model supports". Where the registry knows the
    model, ``max_input_tokens`` is the number that matters: the output reservation
    is not part of the prompt we are sizing.
    """
    ceiling = int(CONFIG.max_context_tokens or 0)
    window = 0
    if model_id:
        try:
            from suzent.core.model_registry import get_model_registry

            caps = get_model_registry().get_capabilities(model_id)
            if caps:
                window = int(caps.max_input_tokens or caps.context_window or 0)
        except Exception as e:
            logger.debug(f"Context window lookup failed for {model_id}: {e}")

    if window <= 0:
        return ceiling or DEFAULT_CONTEXT_LIMIT_TOKENS
    return min(window, ceiling) if ceiling > 0 else window


def build_post_compaction_usage(
    context_tokens: int, context_limit: Optional[int] = None
) -> dict[str, Any]:
    """Build a context-window usage payload reflecting the post-compaction total.

    The frontend usage panel is normally fed by provider-reported usage from the
    last model request, which compaction never touches — so it stays stale until
    the next turn. Every compaction path emits this via ``emit_compaction_event``
    (stage="complete") so all surfaces update the same way. Cumulative/cache fields
    are reset; the next real request repopulates them.
    """
    payload: dict[str, Any] = {
        "input_tokens": context_tokens,
        "output_tokens": 0,
        "total_tokens": context_tokens,
        "context_tokens": context_tokens,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "requests": 0,
        "details": {},
    }
    if context_limit:
        payload["context_limit"] = int(context_limit)
    return payload


def build_live_context_usage(
    context_tokens: int, usage: Any = None, context_limit: Optional[int] = None
) -> dict[str, Any]:
    """Build a partial usage payload describing the context window right now.

    Only ``context_tokens`` is always known mid-run; the cumulative counters come
    from the run's usage so far and are omitted while they are still zero, so a
    consumer can merge this over the previous turn's numbers without blanking
    them at the start of a run.
    """
    payload: dict[str, Any] = {"context_tokens": context_tokens}
    # The limit travels with the count: it depends on the model this turn is
    # running on, so a panel that assumed one global number would draw the wrong
    # percentage as soon as the chat switched models.
    if context_limit:
        payload["context_limit"] = int(context_limit)
    for field in (
        "input_tokens",
        "output_tokens",
        "cache_write_tokens",
        "cache_read_tokens",
        "requests",
    ):
        value = getattr(usage, field, 0) or 0
        if value:
            payload[field] = int(value)
    details = getattr(usage, "details", None)
    if details:
        payload["details"] = dict(details)
    if "input_tokens" in payload or "output_tokens" in payload:
        payload["total_tokens"] = payload.get("input_tokens", 0) + payload.get(
            "output_tokens", 0
        )
    return payload


def emit_context_usage_event(
    *,
    chat_id: str,
    context_tokens: int,
    usage: Any = None,
    context_limit: Optional[int] = None,
    context_breakdown: dict[str, Any] | None = None,
) -> None:
    """Broadcast the live context-window size to every connected client.

    Provider-reported usage only lands when a run *finishes*, so on a long
    tool-heavy turn the context panel would sit on the previous turn's number
    until the whole turn completed. The history processor runs before every model
    request and already knows the size of the history it is about to send, which
    makes it the one place that can report growth as it happens.
    """
    if not chat_id:
        return
    try:
        from suzent.core.stream_registry import emit_bus_event

        emit_bus_event(
            {
                "event": "context_usage",
                "chat_id": chat_id,
                "usage": build_live_context_usage(
                    context_tokens, usage, context_limit=context_limit
                )
                | (
                    {"context_breakdown": context_breakdown}
                    if context_breakdown is not None
                    else {}
                ),
            }
        )
    except Exception as e:
        logger.debug(f"Failed to emit context usage for {chat_id}: {e}")


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
    context_limit: Optional[int] = None,
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
        usage_data = build_post_compaction_usage(tokens_after, context_limit)
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


# Share of the context window the non-history part of a prompt (system prompt +
# every tool schema) can plausibly occupy. Past this, the measurement is not
# overhead but a stale reading taken against a history that no longer exists.
#
# It has to scale with the window rather than sit at a fixed token count: a
# deferred-tool-heavy setup can legitimately carry five figures of schemas, so a
# low fixed ceiling would discard real overhead and compact too late, while a
# ceiling at the window itself can never reject anything (no measurement can
# exceed the window) — which is how the stale-reading guard came to be dead code.
MAX_PLAUSIBLE_CONTEXT_OVERHEAD_RATIO = 0.5


def _part_tokens(part: Any) -> int:
    """Tokens a single message part contributes to the prompt.

    Tool *arguments* count as well as content: a tool call that writes a file
    carries the whole file in ``args`` and nothing in ``content``, so counting
    only content made the largest thing an agent ever sends invisible.
    """
    if isinstance(part, ToolReturnPart):
        content: Any = part.model_response_str_and_user_content()[0]
    else:
        content = getattr(part, "content", "") or ""
    if isinstance(content, (list, tuple)):
        # Images and other binary media are not text; their repr is base64-sized.
        content = "".join(
            item if isinstance(item, str) else item.content
            for item in content
            if isinstance(item, (str, TextContent))
        )
    tokens = estimate_text(content if isinstance(content, str) else str(content))
    args = getattr(part, "args", None)
    if args:
        tokens += estimate_text(args if isinstance(args, str) else str(args))
    return tokens


def estimate_history_tokens(messages: list) -> int:
    """Script-aware estimate over the message history alone."""
    return sum(
        _part_tokens(part) for msg in messages for part in getattr(msg, "parts", [])
    )


def measured_overhead_tokens(
    messages: list, limit: Optional[int] = None
) -> Optional[int]:
    """Tokens the real prompt carries beyond the message history itself.

    The system prompt and every tool's JSON schema are sent on each request but
    never appear in ``messages``, so estimating the history alone reads low by a
    large and roughly constant amount — the gap behind a panel reading 2.7k for a
    prompt the provider counted as five figures.

    Recovering that offset from the provider's own count for the most recent
    request keeps the total honest without anchoring on it: the offset is the
    part that does *not* change as the conversation grows, so the estimate stays
    proportional to the history and still falls when compaction shrinks it. That
    matters — a metric that cannot drop after a compaction would re-trigger
    compaction on every subsequent request of the run.

    ``None`` means there is no usable measurement, as opposed to a measured
    overhead of zero.
    """
    for index in range(len(messages) - 1, -1, -1):
        usage = getattr(messages[index], "usage", None)
        measured = int(getattr(usage, "input_tokens", 0) or 0)
        if measured:
            # `input_tokens` is pydantic-ai's normalized total prompt size for
            # that request — cache reads and writes included — and the request
            # that produced this response was everything before it.
            overhead = measured - estimate_history_tokens(messages[:index])
            ceiling = int(
                (limit or resolve_context_limit())
                * MAX_PLAUSIBLE_CONTEXT_OVERHEAD_RATIO
            )
            if overhead > ceiling:
                # The gap is far too large to be a system prompt and tool
                # schemas: this response was produced *before* a compaction
                # rewrote the history behind it, so its prompt covered messages
                # that are no longer here. Report no offset rather than an
                # offset that would hide the reduction compaction just made.
                return None
            return max(0, overhead)
    return None


def context_overhead_tokens(messages: list, limit: Optional[int] = None) -> int:
    """Measured prompt overhead, or 0 when no usable measurement exists."""
    return measured_overhead_tokens(messages, limit) or 0


def estimate_tokens(
    messages: list, limit: int, fallback_overhead: int = 0
) -> TokenBudget:
    """Best available size of the context window these messages represent.

    This is the one estimate behind both the compaction trigger and the context
    panel. ``fallback_overhead`` is a text estimate of the system prompt and tool
    schemas, used only until the provider has measured a request to calibrate
    against.
    """
    overhead = measured_overhead_tokens(messages, limit)
    return TokenBudget(
        estimated_tokens=estimate_history_tokens(messages)
        + (fallback_overhead if overhead is None else overhead),
        limit=limit,
        trigger_threshold=CONFIG.context_compaction_trigger,
        soft_trim_threshold=CONFIG.context_soft_trim_threshold,
        hard_trim_threshold=CONFIG.context_hard_trim_threshold,
    )


# ---------------------------------------------------------------------------
# Phase 2 — Multi-Layer Tool Result Trimming
# ---------------------------------------------------------------------------


#: Matches the marker a soft trim leaves between head and tail.
_SOFT_TRIM_MARKER = re.compile(r"\n\.\.\. \[\d+ chars trimmed\] \.\.\.\n")


class ToolResultTrimmer:
    """Shrink old tool results before a request, without churning the cache.

    The trimmed history is what the run returns, so it is persisted and sent
    again next turn. Two things keep that resend byte-identical: the boundary
    advances in steps of TRIM_STEP messages rather than with every message,
    and trimming an already trimmed result is a no-op. Either one moving by a
    single message each turn rewrote content the provider had already cached.
    A hard clear ignores the step: it only runs over the hard limit, where
    freeing space comes before the cache.
    """

    SOFT_HEAD = 1000
    SOFT_TAIL = 500
    HARD_PLACEHOLDER = "[Tool output cleared to free context space]"
    #: Messages the trim boundary advances by. A turn with a few tool calls adds
    #: about this many, so most turns leave the boundary where it was.
    TRIM_STEP = 16

    @classmethod
    def trim_cutoff(cls, message_count: int, *, stepped: bool = True) -> int:
        """Index before which tool results may be trimmed.

        Stepped, it is rounded down to a multiple of TRIM_STEP, so it holds
        still while the history grows and up to TRIM_STEP - 1 extra messages
        stay untrimmed. A hard clear is an emergency over the limit and uses the
        exact cutoff: rounding would leave short histories untouched.
        """
        keep_recent = CONFIG.compaction_keep_recent_turns * 2
        cutoff = max(0, message_count - keep_recent)
        return cutoff - cutoff % cls.TRIM_STEP if stepped else cutoff

    @classmethod
    def _rewrite_old_results(
        cls, messages: list, rewrite: Callable[[str], str], *, stepped: bool
    ) -> list:
        cutoff = cls.trim_cutoff(len(messages), stepped=stepped)
        result = []
        for i, msg in enumerate(messages):
            if i >= cutoff or not isinstance(msg, ModelRequest):
                result.append(msg)
                continue
            new_parts = []
            changed = False
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    content = str(part.content or "")
                    rewritten = rewrite(content)
                    if rewritten != content:
                        part = dataclasses.replace(part, content=rewritten)
                        changed = True
                new_parts.append(part)
            result.append(dataclasses.replace(msg, parts=new_parts) if changed else msg)
        return result

    @classmethod
    def _soft(cls, content: str) -> str:
        if len(content) <= cls.SOFT_HEAD + cls.SOFT_TAIL + 20:
            return content
        if _SOFT_TRIM_MARKER.fullmatch(content[cls.SOFT_HEAD : -cls.SOFT_TAIL]):
            return content
        return (
            content[: cls.SOFT_HEAD]
            + f"\n... [{len(content) - cls.SOFT_HEAD - cls.SOFT_TAIL} chars trimmed] ...\n"
            + content[-cls.SOFT_TAIL :]
        )

    @classmethod
    def _hard(cls, content: str) -> str:
        return cls.HARD_PLACEHOLDER if len(content) > 200 else content

    @classmethod
    def apply_soft_trim(cls, messages: list, budget: TokenBudget) -> list:
        """Truncate large ToolReturnPart content to head + tail for older messages."""
        return cls._rewrite_old_results(messages, cls._soft, stepped=True)

    @classmethod
    def apply_hard_clear(cls, messages: list, budget: TokenBudget) -> list:
        """Replace ToolReturnPart content with placeholder for oldest messages."""
        return cls._rewrite_old_results(messages, cls._hard, stepped=False)


# ---------------------------------------------------------------------------
# Main compressor
# ---------------------------------------------------------------------------


def _clear_stale_usage(messages: list) -> list:
    """Drop provider usage from messages carried across a compaction.

    ``usage.input_tokens`` on a retained tail message describes the prompt that
    produced it — a prompt that included the history compaction has just thrown
    away. Left in place, ``context_overhead_tokens`` reads that number against
    the new, much shorter history and reports the discarded messages as fixed
    overhead, so the estimate never falls and compaction re-fires forever.
    """
    cleared = []
    for msg in messages:
        usage = getattr(msg, "usage", None)
        if usage is not None and int(getattr(usage, "input_tokens", 0) or 0):
            try:
                msg = dataclasses.replace(msg, usage=type(usage)())
            except Exception:  # pragma: no cover - non-dataclass message types
                pass
        cleared.append(msg)
    return cleared


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
        model_id: Optional[str] = None,
    ):
        if llm_client:
            self.llm_client = llm_client
        else:
            config = get_effective_memory_config()
            self.llm_client = LLMClient(model=config["extraction_model"])

        self.chat_id = chat_id
        self.user_id = user_id
        # Model the conversation runs on — decides how much context there is to
        # spend before compaction has to step in.
        self.model_id = model_id

    @property
    def context_limit(self) -> int:
        """Token budget for this conversation's model, resolved per call.

        Not cached: the registry can be reloaded (capability sync) and a chat can
        be reopened on a different model within the process's lifetime.
        """
        return resolve_context_limit(self.model_id)

    async def compress_messages(self, messages: list) -> list:
        """Check if message history needs compression and perform it if necessary."""
        if not messages:
            return messages

        budget = estimate_tokens(messages, self.context_limit)
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
            logger.warning("Compaction timed out; preserving original history")
            return messages
        except Exception as e:
            logger.error(f"Context compression failed: {e}")
            return messages

    def get_auto_compaction_plan(self, messages: list) -> dict[str, Any]:
        """Compute whether an automatic compaction attempt should be made."""
        budget = estimate_tokens(messages, self.context_limit)
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
        end_index = safe_tool_history_tail_start(messages, len(messages) - keep_recent)

        if start_index >= end_index:
            return messages

        messages_to_compress = messages[start_index:end_index]

        # Pre-compaction memory flush
        if background_flush:
            self._schedule_memory_flush()
        else:
            await self._flush_pending_memories()

        # Adaptive chunk size
        budget = estimate_tokens(messages, self.context_limit)
        chunk_size = CONFIG.compaction_chunk_size
        if len(messages_to_compress) > 0:
            avg_tokens = budget.estimated_tokens / len(messages)
            if avg_tokens > 2000:
                chunk_size = max(1, chunk_size // 2)

        # Chunked or single-pass summarization
        if len(messages_to_compress) > chunk_size:
            summary = await self._chunked_summarize(
                messages_to_compress, chunk_size, focus
            )
        else:
            summary = await self._summarize_with_retry(messages_to_compress, focus)

        if not summary:
            raise CompactionError(
                "Compaction failed to produce a complete summary. Original history preserved."
            )

        # Preserve the actual active request, including images/files. A text
        # quote in the summary alone cannot carry a multimodal user request.
        active_request = []
        for index in range(len(messages) - 1, 0, -1):
            message = messages[index]
            if not isinstance(message, ModelRequest):
                continue
            prompts = [
                part
                for part in message.parts
                if isinstance(part, UserPromptPart)
                and not is_compaction_summary_text(_user_prompt_text(part))
            ]
            if prompts:
                if index < end_index:
                    active_request = [ModelRequest(parts=prompts)]
                break

        new_messages = (
            messages[:1]
            + build_summary_pair(summary, messages)
            + active_request
            + _clear_stale_usage(messages[end_index:])
        )

        if estimate_history_tokens(new_messages) >= estimate_history_tokens(messages):
            return messages

        logger.info(
            f"Message history compressed: {len(messages)} → {len(new_messages)} messages"
        )
        self._history_rewritten()
        return new_messages

    def _history_rewritten(self) -> None:
        """Let core memory re-pin: the cached prefix is gone either way, and the
        update reminders the old pin relied on may have been summarized away."""
        if self.chat_id:
            from suzent.memory.core_memory_pin import core_memory_pins

            core_memory_pins.forget(self.chat_id)

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
                max_tokens=SUMMARY_MAX_TOKENS,
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

        return ""

    async def _chunked_summarize(
        self, messages: list, chunk_size: int, focus: Optional[str] = None
    ) -> str:
        """Split into chunks, summarize in parallel, then merge."""
        chunks = [
            messages[i : i + chunk_size] for i in range(0, len(messages), chunk_size)
        ]

        semaphore = asyncio.Semaphore(3)

        async def summarize_chunk(chunk: list) -> str:
            async with semaphore:
                return await self._summarize_with_retry(chunk, focus)

        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(summarize_chunk(chunk)) for chunk in chunks]
        partial_summaries = [task.result() for task in tasks]
        if not all(partial_summaries):
            return ""
        combined = "\n\n---\n\n".join(partial_summaries)

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
            max_tokens=SUMMARY_MAX_TOKENS,
        )
        body = extract_summary_body(merged)
        return body if all(section in body for section in REQUIRED_SECTIONS) else ""

    def _schedule_memory_flush(self) -> None:
        """Run the pre-compaction memory flush as a fire-and-forget background task.

        Used from the mid-run history processor so memory extraction never blocks
        the model request that triggered compaction.
        """
        try:
            from suzent.core.task_registry import register_background_task
            import uuid as _uuid

            asyncio.ensure_future(
                register_background_task(
                    self._flush_pending_memories(),
                    task_id=f"precompact_flush_{self.chat_id or 'nochat'}_{_uuid.uuid4().hex}",
                    description=f"Pre-compaction memory flush for chat {self.chat_id}",
                )
            )
        except Exception as e:
            logger.debug(f"Failed to schedule pre-compaction flush: {e}")

    async def _flush_pending_memories(self) -> None:
        """Extract the chat's not-yet-extracted turns before its context shrinks.

        The turns being compacted are still in the transcript, so nothing would be
        lost by waiting; flushing now makes them recallable once the agent no
        longer sees them.
        """
        if not CONFIG.memory_enabled or not self.chat_id or not self.user_id:
            return
        try:
            from suzent.memory.extraction_queue import get_extraction_queue

            await get_extraction_queue().flush(self.chat_id, self.user_id)
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
                    if isinstance(part, UserPromptPart):
                        # User messages are short and critical to intent — keep whole.
                        text.append(f"User: {_user_prompt_text(part)}")
                    elif isinstance(part, ToolReturnPart):
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


def context_input_tokens(
    ctx: Any, messages: list, model_id: Optional[str] = None
) -> int:
    """Best-effort size of the history about to be sent to the model.

    This MUST reflect the current ``messages`` list, because it is the trigger
    metric for mid-run compaction: once a compaction pass shrinks the history,
    the next request has to observe the reduction or the processor re-fires on
    every subsequent request in the run.

    It is the same estimate the context panel shows: the fallback overhead is the
    instruction and tool-schema estimate ``ContextUsageCapability`` recorded for
    the previous request.

    ``ctx.usage.input_tokens`` is deliberately NOT used: pydantic-ai's
    ``RunUsage`` *sums* input tokens across every request in the run (it is a
    monotonically increasing cumulative counter, not the last prompt's size), so
    it can never drop after a compaction and would loop the processor. The
    text estimate over the incoming ``messages`` tracks the compacted list
    directly.
    """
    return estimate_tokens(
        messages,
        resolve_context_limit(model_id),
        getattr(getattr(ctx, "deps", None), "context_overhead_estimate", 0) or 0,
    ).estimated_tokens


# Seconds each chat has spent in mid-run compaction. The pass runs inside the
# stream's wait for the next model event, so without this a summary that took
# longer than the idle window was reported as the model going silent.
_COMPACTION_ELAPSED: dict[str, float] = {}
_COMPACTION_STARTED: dict[str, float] = {}


def compaction_seconds(chat_id: str | None) -> float:
    """Total time ``chat_id`` has spent compacting, including a pass in flight."""
    if not chat_id:
        return 0.0
    started = _COMPACTION_STARTED.get(chat_id)
    running = time.monotonic() - started if started is not None else 0.0
    return _COMPACTION_ELAPSED.get(chat_id, 0.0) + running


@contextlib.contextmanager
def _track_compaction(chat_id: str):
    if not chat_id:
        yield
        return
    _COMPACTION_STARTED[chat_id] = time.monotonic()
    try:
        yield
    finally:
        started = _COMPACTION_STARTED.pop(chat_id)
        _COMPACTION_ELAPSED[chat_id] = (
            _COMPACTION_ELAPSED.get(chat_id, 0.0) + time.monotonic() - started
        )


# Chats where a completed compaction failed to bring the estimate back under the
# trigger, mapped to the estimate it settled at. Compacting again at or below
# that size cannot do better — without this the processor re-summarizes its own
# summary before every request for the rest of the conversation. Growth past the
# recorded size re-arms it, since a longer tail is newly compactible.
_COMPACTION_INEFFECTIVE_AT: dict[str, int] = {}


def reset_compaction_suppression(chat_id: str = "") -> None:
    """Clear the "compaction did not help" marker for a chat (or all chats)."""
    if chat_id:
        _COMPACTION_INEFFECTIVE_AT.pop(chat_id, None)
    else:
        _COMPACTION_INEFFECTIVE_AT.clear()


def make_compaction_history_processor(
    source: str = "auto_midrun", model_id: Optional[str] = None
):
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

        chat_id = getattr(deps, "chat_id", "") or ""
        limit = resolve_context_limit(model_id)
        trigger = limit * CONFIG.context_compaction_trigger
        # The panel is fed by ContextUsageCapability, which sees the final request
        # and its tool schemas; reporting here too made the panel alternate
        # between two readings of the same request.
        current_tokens = context_input_tokens(ctx, messages, model_id)

        if current_tokens < trigger:
            return messages

        # A previous pass on this chat completed and still left the estimate over
        # the trigger. Repeating it at the same size only burns a summarization
        # call per request; wait until the history actually grows past that point.
        ineffective_at = _COMPACTION_INEFFECTIVE_AT.get(chat_id)
        if ineffective_at is not None:
            if current_tokens <= ineffective_at:
                return messages
            _COMPACTION_INEFFECTIVE_AT.pop(chat_id, None)

        # Idempotency: if the tail is already summary-framed and we're only just
        # over the line because of the recent turns, another pass can't help.
        keep_recent = CONFIG.compaction_keep_recent_turns * 2
        if len(messages) <= keep_recent + 1:
            return messages
        already_compacted = any(_message_has_compaction_marker(m) for m in messages)

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

        compressor = ContextCompressor(
            chat_id=chat_id, user_id=user_id, model_id=model_id
        )
        try:
            with _track_compaction(chat_id):
                compressed = await asyncio.wait_for(
                    compressor._perform_compression(messages, background_flush=True),
                    timeout=CONFIG.compaction_timeout_seconds,
                )
        except asyncio.TimeoutError:
            emit_compaction_event(
                chat_id=chat_id,
                stage="error",
                source=source,
                messages_before=messages_before,
                tokens_before=tokens_before,
                message="Compaction timed out. Original history preserved.",
            )
            # A failed summary must not silently delete the agent's task state.
            # Pause if the request no longer fits; otherwise the run can proceed.
            if current_tokens >= limit:
                raise CompactionError(
                    "Context is full and compaction timed out. History preserved."
                )
            return messages
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
            if current_tokens >= limit:
                raise CompactionError(
                    "Context is full and compaction failed. History preserved."
                ) from e
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

        tokens_after = context_input_tokens(ctx, compressed, model_id)
        if compressed is messages or tokens_after >= current_tokens:
            # No reduction (e.g. already compacted and nothing else to drop).
            # Nothing here will change until the history grows, and the pass
            # already paid for a summarization call, so stop re-running it.
            if chat_id:
                _COMPACTION_INEFFECTIVE_AT[chat_id] = current_tokens
            # This still has to report a terminal stage: a "start" was already
            # broadcast, and a surface that animates the running pass would spin
            # forever if this path stayed silent.
            emit_compaction_event(
                chat_id=chat_id,
                stage="skipped",
                source=source,
                messages_before=messages_before,
                messages_after=len(compressed),
                tokens_before=tokens_before,
                message="Context compaction skipped - nothing left to compact"
                if already_compacted
                else None,
            )
            return messages

        if tokens_after >= trigger:
            logger.warning(
                f"Compaction left ~{tokens_after} tokens, still at or over the "
                f"trigger (~{int(trigger)}); suppressing further automatic "
                f"compaction for chat {chat_id or '(none)'} until it grows."
            )
            if chat_id:
                _COMPACTION_INEFFECTIVE_AT[chat_id] = tokens_after
        emit_compaction_event(
            chat_id=chat_id,
            stage="complete",
            source=source,
            messages_before=messages_before,
            messages_after=len(compressed),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            context_limit=limit,
        )
        logger.info(
            f"Mid-run compaction: {messages_before} -> {len(compressed)} messages "
            f"(~{tokens_before} -> ~{tokens_after} tokens)"
        )
        return compressed

    async def _capture_request_history(
        ctx: RunContext[AgentDeps], messages: list
    ) -> list:
        processed = await _processor(ctx, messages)
        # Checkpoints must start from the context actually sent to the model,
        # including compaction and injected messages, rather than the run's
        # original (possibly much larger) history.
        ctx.deps.model_request_history = list(processed)
        return processed

    return _capture_request_history
