from __future__ import annotations

from typing import Any


MAX_TRANSCRIPT_CHARS = 12_000


def compact_transcript(messages: list[Any]) -> str:
    """Project recent conversation context into a bounded classifier transcript."""

    parts: list[str] = []
    remaining = MAX_TRANSCRIPT_CHARS
    for message in reversed(messages[-20:]):
        text = str(message)
        if len(text) > 2_000:
            text = text[:2_000] + "…"
        if len(text) > remaining:
            text = text[:remaining]
        if text:
            parts.append(text)
            remaining -= len(text)
        if remaining <= 0:
            break
    return "\n\n".join(reversed(parts))
