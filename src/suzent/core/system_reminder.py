"""
System Reminder: Out-of-band context injection for Suzent agents.

Provides a mechanism for injecting <system-reminder> blocks
into the LLM context transparently (invisible to the user in UI).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Awaitable, Optional, List

from suzent.logger import get_logger

logger = get_logger(__name__)

REMINDER_TAG = "system-reminder"
_STRIP_RE = re.compile(
    r"<system-reminder>.*?</system-reminder>",
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


# Global hooks for always-on context (like dynamic tools or active skills)
_global_hooks: List[Callable[[str, Any], Awaitable[Optional[str]]]] = []


def register_global_hook(hook: Callable[[str, Any], Awaitable[Optional[str]]]) -> None:
    """Register a global async callback to provide system reminder strings."""
    if hook not in _global_hooks:
        _global_hooks.append(hook)


def clear_global_hooks() -> None:
    """Clear all global hooks (mainly for testing)."""
    _global_hooks.clear()


async def build_combined_reminder(
    chat_id: str,
    deps: Any,
    adhoc_reminders: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Merge global hook content and any adhoc per-turn reminder strings.
    Returns the fully wrapped <system-reminder> block, or None.
    """
    parts: list[str] = []

    # 1. Fetch global hooks
    for hook in _global_hooks:
        try:
            content = await hook(chat_id, deps)
            if content:
                parts.append(content.strip())
        except Exception as e:
            logger.warning(f"System Reminder hook {hook.__name__} failed: {e}")

    # 2. Append turn-specific adhoc reminders
    if adhoc_reminders:
        for r in adhoc_reminders:
            if r and r.strip():
                parts.append(r.strip())

    if not parts:
        return None

    return wrap_in_system_reminder("\n\n---\n\n".join(parts))
