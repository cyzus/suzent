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
import threading
import os
import re
import secrets
from typing import Any, Callable, Awaitable, Optional, List, Sequence, Union

from pydantic_ai.tools import RunContext

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

# Marks a recovered display-trigger line as runtime-generated. Only the history
# sanitizer emits it, and sanitize_untrusted_text strips it from anything
# arriving from outside, so a user who copies a visible "[system trigger: ...]"
# label out of the transcript and sends it back cannot have it read as one.
TRIGGER_MARK = ""

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


def render_trigger_block(display_trigger: str) -> str:
    """The trigger exactly as it appears inside the block.

    One definition, because two things need it: the wrap that emits it and the
    budget that has to charge for it. Sizing the trigger by its bare text left
    the envelope uncounted, so a trigger and a fragment that each fit could
    still clear the cap together.
    """
    return (
        f"<{DISPLAY_TRIGGER_TAG}>\n"
        f"{display_trigger.strip()}\n"
        f"</{DISPLAY_TRIGGER_TAG}>\n\n"
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
    # Wrapping is what confers trust: whatever ends up inside these delimiters
    # is read by the model as authenticated runtime context. Fragments are built
    # from user-influenced material — retrieved memories, goal and task text,
    # background agent results, upload paths — so any delimiters they carry are
    # neutralized here rather than at each of the callers that produce them.
    # Doing it at the wrap point means a new reminder source cannot forget.
    content = sanitize_untrusted_text(content)
    if display_trigger:
        display_trigger = sanitize_untrusted_text(display_trigger)

    body = content.strip()
    if display_trigger and display_trigger.strip():
        body = render_trigger_block(display_trigger) + body
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
    text = (
        text.replace(PUA_START, "[reminder-delimiter]")
        .replace(PUA_END, "[reminder-delimiter]")
        # Untrusted text may not carry the runtime's trigger mark.
        .replace(TRIGGER_MARK, "")
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


def sanitize_tool_payload(value: Any) -> Any:
    """Sanitize a tool result, then verify what the model will actually receive.

    The structural walk below cannot be complete on its own, and every attempt
    to make it so has failed the same way: it inspects attributes, while the
    model receives a *serialization*. A Pydantic model can add content through a
    computed field, a serialization alias, or a custom ``model_serializer``; an
    Enum serializes its value rather than its name. None of that is visible from
    ``model_fields``.

    So the walk is treated as best-effort structure preservation, and
    correctness rests on a post-condition instead: render the result the way the
    tool-return serializer will, and if delimiters survive, hand back sanitized
    text. One check, every shape, including shapes nobody has thought of. This
    is the invariant to protect — not any particular branch of the walk.
    """
    cleaned = sanitize_untrusted_payload(value)
    try:
        rendered = _wire_repr(cleaned)
    except Exception:
        logger.warning("Could not render sanitized tool result to verify; redacting")
        return _REDACTED
    verified = sanitize_untrusted_text(rendered)
    if verified != rendered:
        logger.warning(
            f"Reminder delimiters survived structural sanitizing of a "
            f"{type(value).__name__} tool result; replaced with sanitized text"
        )
        return verified
    return cleaned


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
            rebuilt = _rebuild_sequence(
                value, items, frozenset if isinstance(value, frozenset) else set
            )
            return _degrade_if_collapsed(value, rebuilt, "set members")
        if isinstance(value, dict):
            rebuilt = {
                sanitize_untrusted_payload(k, _depth + 1, _seen): (
                    sanitize_untrusted_payload(v, _depth + 1, _seen)
                )
                for k, v in value.items()
            }
            return _degrade_if_collapsed(value, rebuilt, "mapping keys")

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

        # Unrecognized shape. Render it the way the *serializer* would and keep
        # it only if that text is clean; otherwise hand back the sanitized text.
        try:
            rendered = _wire_repr(value)
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


def _wire_repr(value: Any) -> str:
    """Render a value the way the tool-return serializer will.

    ``str()`` is not that. An ``Enum`` stringifies to ``Payload.BAD`` while
    pydantic serializes its ``value`` — so a member whose value carries
    delimiters looks clean under ``str()`` and arrives at the model intact.
    Checking the wire form is the only way to know what the model will see.
    """
    try:
        from pydantic_core import to_json

        return to_json(value, fallback=str).decode()
    except Exception:
        return str(value)


def _degrade_if_collapsed(original: Any, rebuilt: Any, what: str) -> Any:
    """Fall back to text when sanitizing merged two distinct entries into one.

    Only the deduplicating containers can lose data this way: a forged string
    and its already-escaped twin become equal, and the set or mapping silently
    keeps one. Lists, tuples and named fields cannot collapse, so they do not
    need this. Corrupting a tool result is not an acceptable way to sanitize it,
    so the whole value degrades to sanitized text that still contains every
    entry.
    """
    if len(rebuilt) == len(original):
        return rebuilt
    logger.warning(
        f"Sanitizing collapsed distinct {what}; returning sanitized text so no "
        "entry is lost"
    )
    return sanitize_untrusted_text(_wire_repr(original))


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


def _split_preserving_own_blocks(text: str, handle_span) -> str:
    """Apply *handle_span* to everything except blocks bearing our own token.

    Both callers need the same split — keep what this process authenticated,
    treat the rest as untrusted — and differ only in what "treat" means.
    """
    if not text:
        return text
    out = []
    last = 0
    for match in _OWN_BLOCK_RE.finditer(text):
        out.append(handle_span(text[last : match.start()]))
        out.append(match.group(0))
        last = match.end()
    out.append(handle_span(text[last:]))
    return "".join(out)


def sanitize_incoming_prompt(text: str) -> str:
    """Neutralize forged delimiters in a message arriving now, losing nothing.

    The ingress counterpart to ``sanitize_stored_user_prompt``. The difference is
    deliberate: stored history may contain machine-authored blocks from earlier
    processes that are stale and safe to drop, but a message being sent right now
    is the user's, and deleting part of it loses words they meant to send. Paste
    a raw reminder block in to ask about it and you should see it echoed back
    escaped, not silently swallowed — and if it was the whole message, not turned
    into an empty turn.

    Blocks carrying our token are preserved, so a runtime-authored cron or
    heartbeat prompt still arrives intact.
    """
    return _split_preserving_own_blocks(text, sanitize_untrusted_text)


def has_authenticated_block(text: str) -> bool:
    """True when *text* contains a reminder block this process wrote.

    Lets the display rebuild record, at the moment a trigger row is first
    created, whether it came from a block the runtime authored — provenance that
    a forged block cannot manufacture, because it cannot produce the token.
    """
    if not text:
        return False
    return bool(_OWN_BLOCK_RE.search(text))


def sanitize_stored_user_prompt(text: str) -> str:
    """Make a user prompt restored from history safe to send again.

    Chats predating this change were never sanitized on the way in, so a forged
    block saved back then is still trusted by the model on every request and
    still hidden from the transcript. Ingress only protects new messages.

    Blocks bearing this process's token are kept. Everything else is handled by
    delimiter kind — see ``_scrub_untrusted_span``. Unlike
    ``sanitize_incoming_prompt`` this may delete content, which is appropriate
    for history (a stale machine-authored block helps nobody) and wrong for a
    message someone is sending now.
    """
    return _split_preserving_own_blocks(text, _scrub_untrusted_span)


_DROPPABLE_BLOCK_RE = re.compile(
    rf"{_ANY_PUA_BLOCK_RE.pattern}|{_ANY_XML_TOKENED_BLOCK_RE.pattern}",
    re.DOTALL | re.IGNORECASE,
)


_TRIGGER_PLACEHOLDER_RE = re.compile(
    rf"{TRIGGER_MARK}\[system trigger: .*?\]", re.DOTALL
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
    # Placeholders this function produced on an earlier pass are kept as-is; the
    # processor runs before every request, and re-sanitizing would strip their
    # mark and demote them to ordinary text.
    if _TRIGGER_PLACEHOLDER_RE.search(span):
        out = []
        last = 0
        for found in _TRIGGER_PLACEHOLDER_RE.finditer(span):
            out.append(_scrub_untrusted_span(span[last : found.start()]))
            out.append(found.group(0))
            last = found.end()
        out.append(_scrub_untrusted_span(span[last:]))
        return "".join(out)

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
            pieces.append((True, f"{TRIGGER_MARK}[system trigger: {inner}]"))
        last = match.end()
    pieces.append((False, span[last:]))
    return "".join(
        text if verbatim else sanitize_untrusted_text(text) for verbatim, text in pieces
    )


def make_user_prompt_part(content: Any, *, runtime_authored: bool = False) -> Any:
    """Build a ``UserPromptPart`` with its text sanitized. Use this, not the class.

    Every path that puts words in front of the model has to neutralize forged
    reminder delimiters first, and the ones that forgot were found one at a time
    by review rather than by enumeration — steering appended straight to history,
    ACP derived its transcript from a different string than it executed, forking
    replayed stored display text. There is no reason to expect that list was
    complete, so construction goes through one function instead.

    ``tests/core/test_user_prompt_choke_point.py`` fails if a new call site
    constructs ``UserPromptPart`` directly, which is what actually keeps this
    closed; the helper on its own would just be a convention.

    Set *runtime_authored* only for text this process just wrapped itself — the
    chat processor appending a reminder it built a line earlier. Blocks carrying
    our token survive; everything else is escaped either way. It is not a claim
    about the user's text being safe, only about who assembled the string.
    """
    import dataclasses as _dc

    from pydantic_ai.messages import TextContent, UserPromptPart

    clean = sanitize_incoming_prompt if runtime_authored else sanitize_untrusted_text

    def _clean_item(item: Any) -> Any:
        if isinstance(item, str):
            return clean(item)
        # TextContent is a string tagged with metadata; its `content` is what
        # goes to the LLM, so it needs the same treatment as a bare str. Treating
        # every non-str item as opaque media let it through untouched.
        if isinstance(item, TextContent):
            cleaned = clean(item.content)
            return (
                item if cleaned == item.content else _dc.replace(item, content=cleaned)
            )
        return item

    if isinstance(content, str):
        content = clean(content)
    elif isinstance(content, (list, tuple)):
        items = [_clean_item(item) for item in content]
        content = items if isinstance(content, list) else tuple(items)
    return UserPromptPart(content=content)


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

    # The RunContext annotation is load-bearing: pydantic-ai decides whether to
    # pass a context by inspecting this parameter's *type*, so `ctx: Any` made it
    # call the processor with the message list alone — every request raised
    # TypeError and no sanitizing ran at all.
    async def _processor(ctx: RunContext[Any], messages: list) -> list:
        from pydantic_ai.messages import (
            RetryPromptPart,
            ToolCallPart,
            ToolReturnPart,
            UserPromptPart,
        )

        for message in messages:
            for part in getattr(message, "parts", ()) or ():
                content = getattr(part, "content", None)

                if isinstance(part, UserPromptPart):
                    # Image turns are stored as [text, *media], so a string-only
                    # check would skip every multimodal message.
                    if isinstance(content, str):
                        cleaned = sanitize_stored_user_prompt(content)
                    elif isinstance(content, (list, tuple)):
                        items = [
                            sanitize_stored_user_prompt(item)
                            if isinstance(item, str)
                            else item
                            for item in content
                        ]
                        cleaned = (
                            items
                            if isinstance(content, list)
                            else _rebuild_sequence(content, items, tuple)
                        )
                    else:
                        continue
                    if cleaned != content:
                        part.content = cleaned
                        logger.warning(
                            "Removed unauthenticated reminder blocks from a stored "
                            "user prompt"
                        )
                    continue

                if isinstance(part, (ToolReturnPart, RetryPromptPart)):
                    cleaned = sanitize_tool_payload(content)
                    if cleaned != content:
                        part.content = cleaned
                        logger.warning(
                            "Neutralized forged system-reminder delimiters in output "
                            f"of tool {getattr(part, 'tool_name', '<unknown>')!r}"
                        )
                    continue

                # Everything else that carries text. Model output belongs here:
                # adversarial content can induce the model to emit delimiters in
                # an ordinary TextPart or ThinkingPart — or to reassemble them
                # from escaped tool content — and that response is persisted and
                # replayed as context, where the reminder rules would have the
                # model treat it as trusted. Sanitizing only the compressor's
                # summary covered one producer of model text, not the rest.
                #
                # This branch is deliberately a catch-all rather than a list of
                # part types, so a part type added later is covered by default.
                if isinstance(content, str):
                    cleaned = sanitize_untrusted_text(content)
                    if cleaned != content:
                        part.content = cleaned
                        logger.warning(
                            f"Neutralized reminder delimiters in a "
                            f"{type(part).__name__} of the conversation history"
                        )
                elif isinstance(part, ToolCallPart) and isinstance(
                    getattr(part, "args", None), str
                ):
                    cleaned = sanitize_untrusted_text(part.args)
                    if cleaned != part.args:
                        part.args = cleaned
                        logger.warning(
                            "Neutralized reminder delimiters in tool call arguments"
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


# Fragments inside one reminder block, as build_combined_reminder joins them.
FRAGMENT_SEPARATOR = "\n\n---\n\n"

_ANY_XML_EXTRACT_RE = re.compile(
    rf"<{REMINDER_TAG}(?: nonce=\"{_NONCE_PAT}\")?>(.*?)</{REMINDER_TAG}>",
    re.DOTALL | re.IGNORECASE,
)
_OWN_XML_EXTRACT_RE = re.compile(
    rf"<{REMINDER_TAG} nonce=\"{RUNTIME_NONCE}\">(.*?)</{REMINDER_TAG}>",
    re.DOTALL | re.IGNORECASE,
)


def iter_reminder_fragments(
    text: str, *, authenticated_only: bool = False
) -> list[list[str]]:
    """Provider fragments of each reminder block in *text*, block by block.

    Callers that need to find their own fragment should use this rather than
    scanning lines: the layout has more moving parts than it looks. A block may
    be preceded by the user's message text in the same part, several blocks may
    be concatenated from different turns, and a reminder-only turn prefixes a
    display-trigger envelope inside the wrapper before the body. Re-deriving all
    of that at each call site is how a fragment ends up unfindable.

    Returns one list of fragments per block, in the order the blocks appear.

    With *authenticated_only*, blocks are limited to those this process wrote.
    Callers deciding whether they have already said something need that: this
    runs before the history processor strips unauthenticated blocks, so on the
    first turn after a restart the previous process's reminders are still here,
    and treating them as current means concluding you have spoken when the model
    is about to lose that text.
    """
    if not text:
        return []
    # Ordered by where each block occurs, not by which pattern found it.
    # Concatenating the two result sets put every PUA block before every XML one,
    # so a history spanning a format switch reported the older block as newest.
    patterns = (
        (_PUA_EXTRACT_RE, _OWN_XML_EXTRACT_RE)
        if authenticated_only
        else (_ANY_PUA_EXTRACT_RE, _ANY_XML_EXTRACT_RE)
    )
    found = [
        (match.start(), match.group(1))
        for pattern in patterns
        for match in pattern.finditer(text)
    ]
    found.sort(key=lambda item: item[0])

    blocks = []
    for _, body in found:
        body = _DISPLAY_TRIGGER_RE.sub("", body)
        blocks.append([f for f in body.split(FRAGMENT_SEPARATOR) if f.strip()])
    return blocks


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


#: How long any one reminder provider may take before it is dropped for the turn.
HOOK_TIMEOUT_SECONDS = 2.0

#: How a reminder-only turn's individual reminders are joined into one display
#: trigger.
#:
#: Defined here rather than at the join site because both sides need it: the
#: caller joins with it, and the dedupe below has to split on it to recognise
#: the constituents it is also handed as fragments. Two copies of that string
#: is how the multi-reminder case shipped duplicated.
TRIGGER_SEPARATOR = "\n\n---\n\n"

#: Concurrent blocking providers allowed at once.
#:
#: Deliberately not a ThreadPoolExecutor. Its workers are non-daemon and joined
#: at interpreter exit, so one genuinely wedged read — the case this exists to
#: survive — would hang every server stop, reload and resource-guard recycle,
#: long after the turn itself returned. Daemon threads let the process leave.
#:
#: The bound matters for the same reason the pool did: a stuck thread cannot be
#: killed, so without a ceiling they accumulate. At saturation a caller waits
#: for a slot rather than being dropped — the bound exists to contain wedged
#: threads, and ordinary concurrency is not wedged: a handful of turns running
#: at once routinely needs more than four reads, and skipping them would
#: silently drop context from a perfectly healthy request.
#:
#: The wait is what keeps that safe. It is bounded by the caller's own deadline,
#: so a genuinely wedged provider still stops at HOOK_TIMEOUT_SECONDS instead of
#: queueing behind the block forever.
_PROVIDER_THREADS = 4
_provider_slots = threading.Semaphore(_PROVIDER_THREADS)

#: How often a waiting provider retries the slot. Short enough to be invisible
#: next to the deadline, long enough not to spin.
_SLOT_POLL_SECONDS = 0.01


async def run_provider_blocking(fn: Callable[..., Any], *args: Any) -> Any:
    """Run a reminder provider's blocking work off the event loop.

    Providers that do synchronous I/O must call this. A provider that blocks
    before its first await cannot be timed out at all, because cancelling needs
    the loop to run — so an unreachable network mount or a wedged database
    stalls every turn regardless of HOOK_TIMEOUT_SECONDS.

    Only safe for read-only work. The thread is not cancellable: when the caller
    times out, the work carries on to completion, so anything it writes lands
    after the provider was abandoned.
    """
    # Await a slot rather than taking it or giving up. Blocking the acquire
    # would block the loop — the exact failure this function exists to prevent —
    # so the wait yields, and the caller's timeout cancels it if the pool never
    # frees up. Sleeping here is not a stall: nothing else can start the work.
    while not _provider_slots.acquire(blocking=False):
        await asyncio.sleep(_SLOT_POLL_SECONDS)

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()

    def _deliver(setter: Callable[..., None], value: Any) -> None:
        if not future.done():
            setter(value)

    def _worker() -> None:
        try:
            setter, value = future.set_result, fn(*args)
        except BaseException as exc:  # noqa: BLE001 - relayed to the awaiter
            setter, value = future.set_exception, exc
        finally:
            # Before waking the awaiter, not after. Releasing afterwards let the
            # caller resume while this thread still held the slot, so the pool
            # read as short by one for however long the handoff took — briefly
            # under-subscribed under load, and a genuine race in any check made
            # the moment a provider returns.
            _provider_slots.release()

        try:
            loop.call_soon_threadsafe(_deliver, setter, value)
        except RuntimeError:
            pass  # loop already closed; nobody is waiting

    try:
        threading.Thread(target=_worker, name="reminder-provider", daemon=True).start()
    except BaseException:
        # The slot is released by the worker's finally, so a thread that never
        # starts never gives it back. Four of those and the pool is gone for the
        # life of the process — every provider would then wait out its deadline
        # and plan, skill and repository context would vanish from every turn.
        _provider_slots.release()
        raise
    return await future


#: Ceiling on the assembled reminder body, in characters.
#:
#: Measured on the text that actually gets sent, not on per-provider
#: declarations. Providers that describe their own size drift from what they
#: emit; the assembled string cannot.
REMINDER_BUDGET_CHARS = 6000


def _dedupe_fragments(parts: list[str]) -> list[str]:
    """Drop fragments identical to one already present, keeping the first.

    Two providers can produce the same text — a task list surfaced by both the
    plan hook and an ad-hoc caller, say — and paying for it twice buys nothing.
    """
    seen: set[str] = set()
    unique = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        unique.append(part)
    return unique


def _apply_budget(parts: list[str], chat_id: str, reserved: int = 0) -> list[str]:
    """Keep the assembled body under REMINDER_BUDGET_CHARS.

    Fragments arrive already sanitized, because that is what gets sent.
    Measuring the raw text was wrong by a wide margin: sanitizing expands each
    one-character PUA delimiter into ``[reminder-delimiter]``, and goal, task
    and retrieved-memory text is user-influenced, so a body that measured under
    the cap could arrive many times over it.

    *reserved* accounts for text prepended inside the block that is not a
    fragment — the display trigger — so the cap covers everything the model
    reads rather than only the part this function happens to hold.

    Whole fragments are dropped from the end rather than characters from the
    middle: half a plan snapshot is worse than none, because the model cannot
    tell it is reading a fragment.

    One fragment may exceed the cap on its own, and only one: an empty body is
    indistinguishable from a provider that produced nothing, so something has to
    survive. That exemption is spent by the trigger when there is one. The
    trigger is already going out, so nothing is lost by holding every fragment
    to the cap behind it — whereas exempting the first fragment *as well* let a
    5,900-character trigger and an ordinary plan reminder clear 6,400 together,
    which is the cap failing in exactly the case it was added for.
    """
    separator_cost = len(FRAGMENT_SEPARATOR)
    kept: list[str] = []
    used = reserved
    for index, part in enumerate(parts):
        cost = len(part) + (separator_cost if kept else 0)
        delivered = bool(kept) or reserved > 0
        if delivered and used + cost > REMINDER_BUDGET_CHARS:
            dropped = len(parts) - index
            logger.warning(
                f"[system-reminder] chat={chat_id} over budget: dropped {dropped} "
                f"of {len(parts)} fragment(s) at {used}/{REMINDER_BUDGET_CHARS} chars"
            )
            break
        kept.append(part)
        used += cost
    return kept


async def build_combined_reminder(
    chat_id: str,
    deps: Any,
    adhoc_reminders: Optional[List[str]] = None,
    user_message: Optional[str] = None,
    display_trigger: Union[str, Sequence[str], None] = None,
) -> Optional[str]:
    """Merge all reminder sources into a single wrapped ``<system-reminder>`` block.

    Args:
        chat_id: Active chat session identifier.
        deps: AgentDeps instance (passed through to hooks).
        adhoc_reminders: Caller-supplied one-off strings for this turn.
        user_message: Current user message text.  When non-empty, per-turn
            hooks are also invoked (e.g. dynamic RAG memory retrieval).
        display_trigger: The reminder(s) this turn exists to deliver, shown in
            the transcript. Pass the constituents, not a joined string: they are
            also handed in as fragments, and recovering the boundaries by
            splitting the join cannot work — a reminder whose own text contains
            the separator, such as a Markdown rule, splits into pieces that
            match nothing and is then sent twice. Joining is this module's job
            because deduplicating is too.

    Returns:
        A fully wrapped ``<system-reminder>`` string, or ``None`` if nothing
        was produced.
    """
    parts: list[str] = []

    async def _run(hook, *args) -> Optional[str]:
        """Run one provider under a timeout, never letting it fail the turn."""
        try:
            return await asyncio.wait_for(hook(*args), timeout=HOOK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(
                f"Reminder hook {hook.__name__} timed out after "
                f"{HOOK_TIMEOUT_SECONDS}s — skipped"
            )
        except Exception as e:
            logger.warning(f"Reminder hook {hook.__name__} failed: {e}")
        return None

    # Providers are independent, so they run together. Serially, a slow one
    # delayed every one after it — and global hooks had no timeout at all, so a
    # single hung provider stalled the whole message pipeline indefinitely.
    scheduled = [(hook, _run(hook, chat_id, deps)) for hook in _global_hooks]
    if user_message and user_message.strip():
        scheduled += [
            (hook, _run(hook, chat_id, deps, user_message)) for hook in _per_turn_hooks
        ]

    if scheduled:
        # Registration order is the priority order, and gather preserves it, so
        # what a caller registered first is what survives truncation.
        for content in await asyncio.gather(*(coro for _, coro in scheduled)):
            if content and content.strip():
                parts.append(content.strip())

    # Caller-supplied directives go first, so they survive truncation. They are
    # specific to this turn — a peer's attribution, the analyze_image directive
    # for a non-vision model — while hook output is ambient and reproducible on
    # the next turn. Appending them last meant ambient content could crowd out
    # the one instruction the turn actually depended on.
    direct = [r.strip() for r in (adhoc_reminders or []) if r and r.strip()]
    parts = direct + parts

    # Sanitize before measuring: this is the text that gets sent. wrap_in_system
    # _reminder sanitizes again, which is a no-op on already-clean text.
    parts = [sanitize_untrusted_text(part) for part in parts]
    parts = _dedupe_fragments(parts)

    # A reminder-only turn passes the same text as display_trigger and as an
    # ad-hoc fragment, and the trigger is prepended inside the block — so the
    # model saw it twice and it was charged twice. Dropping the fragment keeps
    # the content (the trigger envelope carries it) and halves the cost.
    # A string is one constituent, not a join to be taken apart. Every earlier
    # version of this recovered the boundaries by splitting the rendered
    # trigger, which is unrecoverable in general and wrong whenever a reminder
    # contains the separator itself.
    _constituents = (
        [display_trigger]
        if isinstance(display_trigger, str)
        else list(display_trigger or [])
    )
    _constituents = _dedupe_fragments(
        [c.strip() for c in _constituents if c and c.strip()]
    )
    # Deduplicated like any other repeated content: the fragments already are,
    # so leaving the trigger alone meant one repeated reminder went out in full
    # twice and could clear the cap on its own through the oversized exemption.
    display_trigger = TRIGGER_SEPARATOR.join(_constituents) or None

    if _constituents:
        # The same strings arrive as fragments, and the trigger is prepended
        # inside the block, so without this the model reads and pays for each
        # one twice.
        charged = {sanitize_untrusted_text(c).strip() for c in _constituents}
        charged.add(sanitize_untrusted_text(display_trigger).strip())
        parts = [part for part in parts if part not in charged]

    # The trigger is prepended inside the block, so it spends from the same
    # budget; without this the cap covered only part of what the model reads.
    trigger_cost = (
        len(render_trigger_block(sanitize_untrusted_text(display_trigger)))
        if display_trigger
        else 0
    )
    parts = _apply_budget(parts, chat_id, reserved=trigger_cost)

    if not parts and not display_trigger:
        logger.debug(f"[system-reminder] chat={chat_id} — no content, skipping")
        return None
    if not parts:
        # Dropping the duplicate fragment can empty the body while a trigger is
        # still owed: a reminder-only turn's whole visible record is that
        # trigger, so returning None here would lose the row entirely.
        logger.debug(f"[system-reminder] chat={chat_id} — trigger only")

    # The separator is in-band, so a fragment carrying it verbatim would split
    # into two and let its own content pose as a separate provider's. Goal and
    # task text is unrestricted, so collapse the blank lines that make it a
    # boundary: the rule stays visible and no characters are lost.
    result = wrap_in_system_reminder(
        FRAGMENT_SEPARATOR.join(
            part.replace(FRAGMENT_SEPARATOR, "\n---\n") for part in parts
        ),
        display_trigger=display_trigger,
    )
    # Metadata only. The wrapped text carries RUNTIME_NONCE, and file logging
    # records DEBUG unconditionally — writing it to disk would hand the token to
    # anyone who can read the logs, which is exactly the forgery this guards
    # against. It also spills retrieved memories, goals and local paths.
    logger.debug(
        f"[system-reminder] chat={chat_id} parts={len(parts)} chars={len(result)}"
    )
    return result
