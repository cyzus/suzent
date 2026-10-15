"""Predict the user's next chat message, shown as ghost text in the composer."""

import asyncio
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

SUGGESTION_TIMEOUT_SECONDS = 8.0
MAX_CONTEXT_MESSAGES = 6
MAX_MESSAGE_CHARS = 1500
MAX_SUGGESTION_CHARS = 200

_NO_SUGGESTION = "NONE"

_SYSTEM_PROMPT = (
    "You predict what the user will type next in a chat with an AI agent. "
    "You are not replying to anyone. Read the conversation and write the "
    "single most likely next message from the USER: a short, natural follow-up "
    "such as a request to continue, a clarifying question, or the obvious next "
    "step. Write it in the language the user has been using, in their voice, "
    "as plain text on one line, at most 15 words, with no quotes or preamble. "
    f"If there is no confident prediction, output exactly {_NO_SUGGESTION}."
)


def _message_text(message: dict[str, Any]) -> str:
    from suzent.core.system_reminder import strip_system_reminders

    content = message.get("content")
    if not isinstance(content, str):
        return ""
    text = " ".join(strip_system_reminders(content).split())
    if len(text) > MAX_MESSAGE_CHARS:
        text = f"…{text[-MAX_MESSAGE_CHARS:]}"
    return text


def build_transcript(messages: list[dict[str, Any]]) -> str | None:
    """Render the recent conversation, or None when no prediction makes sense.

    A prediction only fits once the agent has had the last word: while the
    user's own message is the latest one, they are waiting, not typing.
    """
    turns = [
        (m.get("role"), _message_text(m))
        for m in messages
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    turns = [(role, text) for role, text in turns if text]
    if not turns or turns[-1][0] != "assistant":
        return None
    if not any(role == "user" for role, _ in turns):
        return None

    recent = turns[-MAX_CONTEXT_MESSAGES:]
    return "\n".join(
        f'<{role} message="{i}">\n{text}\n</{role}>'
        for i, (role, text) in enumerate(recent, start=1)
    )


def clean_suggestion(raw: str | None) -> str | None:
    """Normalize model output into one line of ghost text, or None to show nothing."""
    if not raw:
        return None
    line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    line = line.strip().strip("\"'“”‘’`").strip()
    if not line or line.upper().rstrip(".") == _NO_SUGGESTION:
        return None
    if len(line) > MAX_SUGGESTION_CHARS:
        return None
    return line


async def _suggest_with_model(model: str, transcript: str) -> str | None:
    from suzent.llm import LLMClient

    client = LLMClient(model=model)
    raw = await client.complete(
        prompt=(
            f"<conversation>\n{transcript}\n</conversation>\nThe user's next message:"
        ),
        system=_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=256,
        reasoning_effort="none",
    )
    return clean_suggestion(raw)


async def suggest_next_input(messages: list[dict[str, Any]]) -> str | None:
    """Return a predicted next user message for a conversation, or None.

    Uses the ``suggestion`` role, which inherits the cheap model. Every failure
    yields None: the feature is a convenience and must never surface an error.
    """
    from suzent.core.role_router import ModelRole, get_role_router

    transcript = build_transcript(messages)
    if transcript is None:
        return None

    model = get_role_router().get_model_id(ModelRole.SUGGESTION)
    if not model:
        return None

    try:
        return await asyncio.wait_for(
            _suggest_with_model(model, transcript),
            timeout=SUGGESTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.debug(f"Input suggestion timed out (model={model!r})")
    except Exception as e:
        logger.warning(f"Input suggestion failed (model={model!r}): {type(e).__name__}")
    return None
