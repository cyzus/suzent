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
import re
from typing import Any, Callable, Awaitable, Optional, List

from suzent.logger import get_logger

logger = get_logger(__name__)

REMINDER_TAG = "system-reminder"
_STRIP_RE = re.compile(
    r"<system-reminder>.*?</system-reminder>",
    re.DOTALL | re.IGNORECASE,
)
_EXTRACT_RE = re.compile(
    r"<system-reminder>(.*?)</system-reminder>",
    re.DOTALL | re.IGNORECASE,
)


def wrap_in_system_reminder(content: str) -> str:
    """Wrap content in a <system-reminder> xml tag block."""
    return f"\n<{REMINDER_TAG}>\n{content.strip()}\n</{REMINDER_TAG}>\n"


def strip_system_reminders(text: str) -> str:
    """Remove all <system-reminder>...</system-reminder> blocks from text."""
    if not text:
        return text
    return _STRIP_RE.sub("", text).strip()


def extract_system_reminder_content(text: str) -> str:
    """Return the concatenated inner text of all <system-reminder> blocks."""
    if not text:
        return ""
    parts = [m.strip() for m in _EXTRACT_RE.findall(text) if m.strip()]
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

    result = wrap_in_system_reminder("\n\n---\n\n".join(parts))
    logger.debug(f"[system-reminder] chat={chat_id} ({len(parts)} part(s)):\n{result}")
    return result
