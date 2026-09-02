"""
System Reminder: Out-of-band context injection for Suzent agents.

Provides a mechanism for injecting <system-reminder> blocks
into the LLM context transparently (invisible to the user in UI).

Two hook types:
- Global hooks  ``(chat_id, deps) -> str | None``
  Run on every turn regardless of content. Useful for always-on signals
  (active skills, tool availability, etc.).
- Per-turn hooks  ``(chat_id, deps, user_message) -> str | None``
  Run only when there is a real user message. Ideal for query-dependent
  retrieval such as dynamic RAG memory injection.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import re
import secrets
from typing import Any, Callable, Awaitable, Optional, List

from suzent.logger import get_logger

logger = get_logger(__name__)

REMINDER_TAG = "system-reminder"
DISPLAY_TRIGGER_TAG = "system-reminder-display-trigger"

# PUA (private-use area) delimiters used to wrap reminder blocks invisibly. The
# citation system already owns U+E200–U+E202 (see Citations.tsx), so we use the
# next free codepoints. These render as nothing in the UI, so reminders stay
# fully hidden without relying on the model to honor an XML tag convention.
PUA_START = ""  # hidden-content start
PUA_END = ""  # hidden-content end

# Per-process runtime token embedded in every reminder we author.
#
# The delimiters above are public constants, so any text that reaches the model
# — a user message, a fetched web page, a tool result — could otherwise carry a
# byte-identical block and be read as trusted out-of-band context. The token
# makes a genuine block unforgeable by anything that cannot read this process's
# memory, and lets the display path tell runtime-authored blocks apart from
# look-alike text a user legitimately typed.
#
# Scope note: the token is embedded in persisted history, so anyone able to read
# a raw transcript can learn it. It is defence in depth behind
# ``sanitize_untrusted_text()``, not a secret to rely on by itself.
RUNTIME_NONCE = secrets.token_hex(8)

_NONCE_PAT = "[0-9a-f]{16}"

# --- Runtime-authored blocks from *this* process ---------------------------
_PUA_STRIP_RE = re.compile(
    rf"{PUA_START}{RUNTIME_NONCE}.*?{RUNTIME_NONCE}{PUA_END}", re.DOTALL
)
_PUA_EXTRACT_RE = re.compile(
    rf"{PUA_START}{RUNTIME_NONCE}(.*?){RUNTIME_NONCE}{PUA_END}", re.DOTALL
)
_STRIP_RE = re.compile(
    rf'<{REMINDER_TAG} nonce="{RUNTIME_NONCE}">.*?</{REMINDER_TAG}>',
    re.DOTALL | re.IGNORECASE,
)
_EXTRACT_RE = re.compile(
    rf'<{REMINDER_TAG}(?: nonce="{RUNTIME_NONCE}")?>(.*?)</{REMINDER_TAG}>',
    re.DOTALL | re.IGNORECASE,
)

# --- Blocks authored by any run of the runtime -----------------------------
# The display path must keep hiding reminders persisted before the last restart,
# whose token differs from ours (or is absent, for pre-nonce history).
_ANY_PUA_STRIP_RE = re.compile(
    rf"{PUA_START}(?:{_NONCE_PAT})?.*?(?:{_NONCE_PAT})?{PUA_END}", re.DOTALL
)
_ANY_XML_STRIP_RE = re.compile(
    rf'<{REMINDER_TAG}(?: nonce="{_NONCE_PAT}")?>.*?</{REMINDER_TAG}>',
    re.DOTALL | re.IGNORECASE,
)
_ANY_PUA_EXTRACT_RE = re.compile(
    rf"{PUA_START}(?:{_NONCE_PAT})?(.*?)(?:{_NONCE_PAT})?{PUA_END}", re.DOTALL
)
_DISPLAY_TRIGGER_RE = re.compile(
    rf"<{DISPLAY_TRIGGER_TAG}>(.*?)</{DISPLAY_TRIGGER_TAG}>",
    re.DOTALL | re.IGNORECASE,
)


def wrap_in_system_reminder(content: str, display_trigger: Optional[str] = None) -> str:
    """Wrap content in a hidden reminder block.

    Defaults to invisible PUA delimiters (``PUA_START``/``PUA_END``). Set the
    ``SUZENT_XML_SYSTEM_REMINDER`` env var to fall back to ``<system-reminder>``
    XML tags, which is easier to read when debugging the raw context.

    The optional ``display_trigger`` is nested as a ``<system-reminder-display-trigger>``
    XML sub-tag *inside* the block regardless of the outer delimiter, so the
    display-rebuild path can still extract it.
    """
    body = content.strip()
    if display_trigger and display_trigger.strip():
        body = (
            f"<{DISPLAY_TRIGGER_TAG}>\n"
            f"{display_trigger.strip()}\n"
            f"</{DISPLAY_TRIGGER_TAG}>\n\n"
            f"{body}"
        )
    if os.environ.get("SUZENT_XML_SYSTEM_REMINDER"):
        return (
            f'\n<{REMINDER_TAG} nonce="{RUNTIME_NONCE}">\n{body}\n</{REMINDER_TAG}>\n'
        )
    return f"\n{PUA_START}{RUNTIME_NONCE}\n{body}\n{RUNTIME_NONCE}{PUA_END}\n"


# Forged tags in untrusted text, in every spelling the display path would later
# recognize: the strippers are case-insensitive, so anything narrower here lets a
# block through to the model *and* hides it from the transcript.
_UNTRUSTED_OPEN_RE = re.compile(rf"<\s*{REMINDER_TAG}(?:\s[^>]*)?>", re.IGNORECASE)
_UNTRUSTED_CLOSE_RE = re.compile(rf"<\s*/\s*{REMINDER_TAG}\s*>", re.IGNORECASE)
_UNTRUSTED_TRIGGER_RE = re.compile(
    rf"<\s*/?\s*{DISPLAY_TRIGGER_TAG}(?:\s[^>]*)?>", re.IGNORECASE
)


def sanitize_untrusted_text(text: str) -> str:
    """Neutralize reminder delimiters in text Suzent did not author.

    Applied to every untrusted string on its way into the model context: user
    messages, attachment text, and tool results. Without this a fetched web page
    or a tool result could carry its own delimiters and be read as trusted
    out-of-band context (prompt injection).

    Delimiters are replaced with a visible marker rather than deleted, so the
    text stays intelligible and the attempt is auditable. Content is otherwise
    left alone.
    """
    if not text:
        return text
    text = text.replace(PUA_START, "[reminder-delimiter]").replace(
        PUA_END, "[reminder-delimiter]"
    )
    text = _UNTRUSTED_OPEN_RE.sub(f"&lt;{REMINDER_TAG}&gt;", text)
    text = _UNTRUSTED_CLOSE_RE.sub(f"&lt;/{REMINDER_TAG}&gt;", text)
    # A forged display-trigger tag would surface attacker text in the UI as though
    # the runtime had raised it.
    return _UNTRUSTED_TRIGGER_RE.sub(f"&lt;{DISPLAY_TRIGGER_TAG}&gt;", text)


# Depth at which we stop descending. Legitimate tool results are nowhere near
# this; the limit exists so a self-referential or pathologically nested payload
# cannot exhaust the stack. Exceeding it redacts rather than passing the value
# through, so the limit can never become a way to smuggle delimiters past us.
_MAX_PAYLOAD_DEPTH = 60
_REDACTED = "[unsanitized content omitted]"


def sanitize_untrusted_payload(
    value: Any, _depth: int = 0, _seen: Optional[set] = None
) -> Any:
    """Sanitize every string a tool result can put in front of the model.

    Tools return structured objects, not strings, and pydantic-ai serializes a
    wide range of shapes: Pydantic models, dataclasses, the usual containers,
    sets, and anything whose ``str()`` it falls back on such as ``pathlib.Path``.

    The traversal is deliberately **fail-closed**. An earlier version listed the
    shapes it understood and returned everything else untouched, which meant each
    unlisted type — a dataclass, then a set, then a Path — was a fresh way for
    forged delimiters to reach the model, found one at a time. Now anything not
    recognized as a container is rendered and checked: if its text carries
    delimiters it is replaced by the sanitized text, so an unfamiliar shape
    degrades to something safe instead of passing through.

    Mapping keys are sanitized as well as values — a tool or MCP response picks
    its own property names, and those are serialized too. Cycles are tracked by
    identity so a self-referential payload terminates.
    """
    if isinstance(value, str):
        return sanitize_untrusted_text(value)
    if value is None or isinstance(
        value, (bool, int, float, complex, bytes, bytearray)
    ):
        return value

    if _depth > _MAX_PAYLOAD_DEPTH:
        logger.warning("Payload nesting exceeded sanitizer depth; redacting branch")
        return _REDACTED

    if _seen is None:
        _seen = set()
    marker = id(value)
    if marker in _seen:
        return value
    _seen.add(marker)
    try:
        if isinstance(value, list):
            return [sanitize_untrusted_payload(v, _depth + 1, _seen) for v in value]
        if isinstance(value, tuple):
            items = [sanitize_untrusted_payload(v, _depth + 1, _seen) for v in value]
            return _rebuild_sequence(value, items, tuple)
        if isinstance(value, (set, frozenset)):
            items = [sanitize_untrusted_payload(v, _depth + 1, _seen) for v in value]
            return _rebuild_sequence(
                value, items, frozenset if isinstance(value, frozenset) else set
            )
        if isinstance(value, dict):
            return {
                sanitize_untrusted_payload(k, _depth + 1, _seen): (
                    sanitize_untrusted_payload(v, _depth + 1, _seen)
                )
                for k, v in value.items()
            }

        if getattr(type(value), "model_fields", None):
            return _sanitize_fields(
                value,
                [name for name in type(value).model_fields],
                lambda obj, updates: obj.model_copy(update=updates),
                _depth,
                _seen,
            )
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return _sanitize_fields(
                value,
                [f.name for f in dataclasses.fields(value)],
                lambda obj, updates: dataclasses.replace(obj, **updates),
                _depth,
                _seen,
            )

        # Unrecognized shape. Render it the way the serializer would and keep it
        # only if that text is clean; otherwise hand back the sanitized text.
        try:
            rendered = str(value)
        except Exception:
            logger.warning(
                f"Could not render {type(value).__name__} to check it; redacting"
            )
            return _REDACTED
        cleaned = sanitize_untrusted_text(rendered)
        if cleaned != rendered:
            logger.warning(
                f"Forged delimiters in a {type(value).__name__} tool result; "
                "replaced with sanitized text"
            )
            return cleaned
        return value
    finally:
        _seen.discard(marker)


def _rebuild_sequence(value: Any, items: list, plain):
    """Rebuild a tuple/set, preserving the subclass only if it accepts the items.

    A NamedTuple takes one argument per field rather than an iterable, so calling
    ``type(value)(items)`` on one raises — which would abort the whole model
    request over a shape pydantic-ai serializes perfectly well. Where the
    subclass cannot be reconstructed, degrading to the plain builtin keeps the
    data and the sanitizing; only the subclass identity is lost, and the
    serializer renders both the same way.
    """
    if isinstance(value, tuple) and hasattr(value, "_fields"):
        try:
            return type(value)(*items)
        except Exception:
            return plain(items)
    if type(value) is plain:
        return plain(items)
    try:
        return type(value)(items)
    except Exception:
        return plain(items)


def _sanitize_fields(value: Any, names: list, rebuild, _depth: int, _seen: set) -> Any:
    """Sanitize named attributes, rebuilding the object when any of them change.

    If an update cannot be applied — a frozen dataclass whose ``__post_init__``
    rejects the sanitized value, say — the object is redacted rather than
    returned as-is. Handing back the original would ship the forged delimiters
    it still contains, which is the one outcome this function exists to prevent.
    """
    updates = {}
    for name in names:
        current = getattr(value, name, None)
        cleaned = sanitize_untrusted_payload(current, _depth + 1, _seen)
        if cleaned != current:
            updates[name] = cleaned
    if not updates:
        return value
    try:
        return rebuild(value, updates)
    except Exception:
        pass
    for name, cleaned in updates.items():
        try:
            setattr(value, name, cleaned)
        except Exception:
            logger.warning(
                f"Could not sanitize {type(value).__name__}.{name}; redacting the "
                "whole value rather than passing it through"
            )
            return _REDACTED
    return value


# Only this process's token authenticates a block. A token *shape* proves
# nothing — an earlier design accepted any 16 hex characters, which meant a
# stored prompt containing PUA_START + "0"*16 + payload + "0"*16 + PUA_END was
# waved through as runtime-authored. Provenance cannot be verified across a
# restart, so blocks we cannot authenticate are not trusted, full stop.
_OWN_BLOCK_RE = re.compile(
    rf"{PUA_START}{RUNTIME_NONCE}.*?{RUNTIME_NONCE}{PUA_END}"
    rf'|<{REMINDER_TAG} nonce="{RUNTIME_NONCE}">.*?</{REMINDER_TAG}>',
    re.DOTALL | re.IGNORECASE,
)

# Any PUA-delimited block, tokenized or not.
_ANY_PUA_BLOCK_RE = re.compile(
    rf"{PUA_START}(?:{_NONCE_PAT})?.*?(?:{_NONCE_PAT})?{PUA_END}", re.DOTALL
)

# A complete XML block carrying a nonce attribute. Nobody hand-writes
# nonce="a1b2c3d4e5f6a7b8", so this is runtime output from some process even when
# the token is not ours, and it gets dropped rather than escaped.
_ANY_XML_TOKENED_BLOCK_RE = re.compile(
    rf'<{REMINDER_TAG} nonce="{_NONCE_PAT}">.*?</{REMINDER_TAG}>',
    re.DOTALL | re.IGNORECASE,
)


def sanitize_stored_user_prompt(text: str) -> str:
    """Make a user prompt restored from history safe to send again.

    Chats predating this change were never sanitized on the way in, so a forged
    block saved back then is still trusted by the model on every request and
    still hidden from the transcript. Ingress only protects new messages.

    Blocks bearing *this process's* token are kept — that is the reminder the
    chat processor appended this turn. Everything else is handled by delimiter
    kind, because the two carry very different odds of being human-authored:

    * PUA blocks are dropped outright. The delimiters are invisible control
      characters nobody types by hand, so an unauthenticated one is either a
      forgery or a reminder from an earlier process. Both should go: the forgery
      is hostile, and the old reminder is stale context whose goal counts and
      task lists now contradict the current turn. Dropping rather than defusing
      also means the transcript does not change — those blocks were already
      hidden, and now they are simply gone.

    * XML blocks carrying a nonce attribute are dropped too. Under
      ``SUZENT_XML_SYSTEM_REMINDER`` a restart leaves every stored reminder
      tagged with the previous process's token; escaping those would leave the
      body behind as text the display path can no longer strip, turning internal
      reminder content into a visible user message.

    * Bare XML tags are escaped rather than dropped. Someone can plausibly type
      ``<system-reminder>`` in a message — discussing this very feature, say —
      and deleting their words would be worse than showing them.
    """
    if not text:
        return text
    out = []
    last = 0
    for match in _OWN_BLOCK_RE.finditer(text):
        out.append(_scrub_untrusted_span(text[last : match.start()]))
        out.append(match.group(0))
        last = match.end()
    out.append(_scrub_untrusted_span(text[last:]))
    return "".join(out)


_DROPPABLE_BLOCK_RE = re.compile(
    rf"{_ANY_PUA_BLOCK_RE.pattern}|{_ANY_XML_TOKENED_BLOCK_RE.pattern}",
    re.DOTALL | re.IGNORECASE,
)


def _scrub_untrusted_span(span: str) -> str:
    """Drop unauthenticated machine-authored blocks; escape what is left.

    Dropping is reserved for shapes no person produces by hand: PUA delimiters,
    and complete XML blocks bearing a nonce attribute. Bare tags survive as
    escaped text so a human's words are never deleted.

    A cron or heartbeat turn carries no user text at all — its whole visible
    record is the ``display_trigger`` nested inside the reminder. Dropping the
    block wholesale would leave an empty prompt, and the next rebuild would
    persist the former ``system_triggered`` row as a blank user message. So the
    trigger is carried across, with its inner text sanitized: the label is
    preserved, the model-only body still goes, and a forged block cannot smuggle
    delimiters back in through the part we keep.
    """
    if not span:
        return span
    pieces: list[tuple[bool, str]] = []
    last = 0
    for match in _DROPPABLE_BLOCK_RE.finditer(span):
        pieces.append((False, span[last : match.start()]))
        trigger = _DISPLAY_TRIGGER_RE.search(match.group(0))
        if trigger:
            # Plain visible text, never a reminder block. Rewrapping this in a
            # block of ours would stamp our token onto content we just decided
            # we cannot authenticate — laundering an attacker's trigger from a
            # forged pre-change prompt into trusted hidden context. Whatever the
            # cosmetic cost, unverifiable text does not get signed.
            #
            # Emitting it as a labelled line keeps the record of what fired
            # (rather than leaving an empty prompt that rebuilds as a blank row)
            # while making it ordinary visible content: not hidden, not trusted.
            inner = sanitize_untrusted_text(trigger.group(1).strip())
            pieces.append((True, f"[system trigger: {inner}]"))
        last = match.end()
    pieces.append((False, span[last:]))
    return "".join(
        text if verbatim else sanitize_untrusted_text(text) for verbatim, text in pieces
    )


def make_tool_output_sanitizer_history_processor():
    """Build a history processor that strips forged delimiters from tool results.

    Tool output is the highest-risk injection surface: a fetched web page, a file
    read, or an MCP server's response can all carry attacker-controlled text, and
    unlike user messages there is no single ingress point to sanitize — pydantic-ai
    builds ``ToolReturnPart`` internally. A history processor is the one chokepoint
    that sees every part before it reaches the model.

    ``UserPromptPart`` is handled too, but through
    ``sanitize_stored_user_prompt`` so the genuine reminder the chat processor
    appends survives. Chats predating this change were never sanitized on the way
    in, so their stored prompts still need cleaning on the way back out.
    """

    async def _processor(ctx: Any, messages: list) -> list:
        from pydantic_ai.messages import (
            RetryPromptPart,
            ToolReturnPart,
            UserPromptPart,
        )

        for message in messages:
            for part in getattr(message, "parts", ()) or ():
                content = getattr(part, "content", None)

                if isinstance(part, UserPromptPart):
                    # Image turns are stored as [text, *media], so a string-only
                    # check would skip every multimodal message. Media items are
                    # passed through untouched.
                    if isinstance(content, str):
                        cleaned = sanitize_stored_user_prompt(content)
                    elif isinstance(content, (list, tuple)):
                        items = [
                            sanitize_stored_user_prompt(item)
                            if isinstance(item, str)
                            else item
                            for item in content
                        ]
                        cleaned = type(content)(items)
                    else:
                        continue
                    if cleaned != content:
                        part.content = cleaned
                        logger.warning(
                            "Removed unauthenticated reminder blocks from a stored "
                            "user prompt"
                        )
                    continue

                if not isinstance(part, (ToolReturnPart, RetryPromptPart)):
                    continue
                cleaned = sanitize_untrusted_payload(content)
                if cleaned != content:
                    part.content = cleaned
                    logger.warning(
                        "Neutralized forged system-reminder delimiters in output of "
                        f"tool {getattr(part, 'tool_name', '<unknown>')!r}"
                    )
        return messages

    return _processor


def strip_system_reminders(text: str) -> str:
    """Remove runtime-authored reminder blocks from text, for display.

    Matches blocks carrying a runtime token — ours or an older process's — plus
    untokenized blocks, which is what history written before tokens existed
    looks like.

    Stripping untokenized blocks is only safe because
    ``sanitize_untrusted_text()`` runs first on every untrusted string, so a
    forged delimiter never survives as a delimiter: it reaches the transcript as
    the literal text ``[reminder-delimiter]`` and stays visible to the user. If
    that ingress step is ever removed, this function starts silently hiding text
    users actually typed.
    """
    if not text:
        return text
    text = _ANY_PUA_STRIP_RE.sub("", text)
    text = _ANY_XML_STRIP_RE.sub("", text)
    return text.strip()


def extract_system_reminder_content(text: str) -> str:
    """Return the concatenated inner text of all reminder blocks (PUA + XML)."""
    if not text:
        return ""
    parts = [m.strip() for m in _ANY_PUA_EXTRACT_RE.findall(text) if m.strip()]
    parts += [m.strip() for m in _EXTRACT_RE.findall(text) if m.strip()]
    return "\n\n".join(parts)


def extract_system_reminder_display_trigger(text: str) -> str:
    """Return user-visible trigger text explicitly marked inside reminders."""
    if not text:
        return ""
    parts = [m.strip() for m in _DISPLAY_TRIGGER_RE.findall(text) if m.strip()]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Global hooks — always-on, no user message required
# ---------------------------------------------------------------------------

_global_hooks: List[Callable[[str, Any], Awaitable[Optional[str]]]] = []


def register_global_hook(hook: Callable[[str, Any], Awaitable[Optional[str]]]) -> None:
    """Register a global async callback to provide system reminder strings.

    Signature: ``async def hook(chat_id: str, deps: AgentDeps) -> str | None``
    """
    if hook not in _global_hooks:
        _global_hooks.append(hook)


def clear_global_hooks() -> None:
    """Clear all global hooks (mainly for testing)."""
    _global_hooks.clear()


# ---------------------------------------------------------------------------
# Per-turn hooks — only called when there is a real user message
# ---------------------------------------------------------------------------

_per_turn_hooks: List[Callable[[str, Any, str], Awaitable[Optional[str]]]] = []


def register_per_turn_hook(
    hook: Callable[[str, Any, str], Awaitable[Optional[str]]],
) -> None:
    """Register an async callback that runs once per user message turn.

    Signature: ``async def hook(chat_id: str, deps: AgentDeps, user_message: str) -> str | None``

    Per-turn hooks are skipped when *user_message* is empty (e.g. heartbeats,
    pure tool-resume turns). Use them for query-dependent retrieval such as
    dynamic RAG memory injection.
    """
    if hook not in _per_turn_hooks:
        _per_turn_hooks.append(hook)


def clear_per_turn_hooks() -> None:
    """Clear all per-turn hooks (mainly for testing)."""
    _per_turn_hooks.clear()


# ---------------------------------------------------------------------------
# Combined reminder builder
# ---------------------------------------------------------------------------


async def build_combined_reminder(
    chat_id: str,
    deps: Any,
    adhoc_reminders: Optional[List[str]] = None,
    user_message: Optional[str] = None,
    display_trigger: Optional[str] = None,
) -> Optional[str]:
    """Merge all reminder sources into a single wrapped ``<system-reminder>`` block.

    Args:
        chat_id: Active chat session identifier.
        deps: AgentDeps instance (passed through to hooks).
        adhoc_reminders: Caller-supplied one-off strings for this turn.
        user_message: Current user message text.  When non-empty, per-turn
            hooks are also invoked (e.g. dynamic RAG memory retrieval).

    Returns:
        A fully wrapped ``<system-reminder>`` string, or ``None`` if nothing
        was produced.
    """
    parts: list[str] = []

    # 1. Global hooks (always-on)
    for hook in _global_hooks:
        try:
            content = await hook(chat_id, deps)
            if content:
                parts.append(content.strip())
        except Exception as e:
            logger.warning(f"System Reminder global hook {hook.__name__} failed: {e}")

    # 2. Per-turn hooks (only when there is a real user message)
    # Each hook runs with a timeout so a slow embedding/search call never
    # stalls the message pipeline. Timed-out hooks are skipped silently.
    _PER_TURN_TIMEOUT = 2.0  # seconds
    if user_message and user_message.strip():
        for hook in _per_turn_hooks:
            try:
                content = await asyncio.wait_for(
                    hook(chat_id, deps, user_message),
                    timeout=_PER_TURN_TIMEOUT,
                )
                if content:
                    parts.append(content.strip())
            except asyncio.TimeoutError:
                logger.debug(
                    f"Per-turn hook {hook.__name__} timed out after {_PER_TURN_TIMEOUT}s — skipped"
                )
            except Exception as e:
                logger.warning(
                    f"System Reminder per-turn hook {hook.__name__} failed: {e}"
                )

    # 3. Caller-supplied adhoc reminders
    if adhoc_reminders:
        for r in adhoc_reminders:
            if r and r.strip():
                parts.append(r.strip())

    if not parts:
        logger.debug(f"[system-reminder] chat={chat_id} — no content, skipping")
        return None

    result = wrap_in_system_reminder(
        "\n\n---\n\n".join(parts), display_trigger=display_trigger
    )
    logger.debug(f"[system-reminder] chat={chat_id} ({len(parts)} part(s)):\n{result}")
    return result
