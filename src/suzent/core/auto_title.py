"""Auto-title generation for new chats using the RoleRouter."""

from typing import Any

from loguru import logger

_PLACEHOLDER_TITLES = frozenset({"", "new chat", "untitled"})


def should_generate_auto_title(chat: Any) -> bool:
    """Generate when first turn or when a previous placeholder title survived."""
    if chat is None:
        return False
    turn_count = getattr(chat, "turn_count", 0) or 0
    if turn_count == 0:
        return True
    title = str(getattr(chat, "title", "") or "").strip().lower()
    return title in _PLACEHOLDER_TITLES


def _clean_title_source(user_content: str) -> str:
    from suzent.core.system_reminder import strip_system_reminders

    return " ".join(strip_system_reminders(user_content).split())


async def _generate_title_with_model(model: str, user_content: str) -> str | None:
    from suzent.llm import LLMClient

    client = LLMClient(model=model)
    title = await client.complete(
        prompt=(
            "Create a title for this user message:\n"
            "<message>\n"
            f"{user_content[:500]}\n"
            "</message>\n"
            "Title:"
        ),
        system=(
            "You name chat conversations. You are not replying to the user. "
            "Write the title in the primary language of the user's message. "
            "Output only a concise chat title of 3 to 6 words. "
            "No punctuation, no quotes."
        ),
        temperature=0.3,
        max_tokens=512,
        reasoning_effort="none",
    )
    return title.strip().strip("\"'").strip() if title else None


async def generate_auto_title(
    chat_id: str, user_content: str, fallback_model: str | None = None
) -> str | None:
    """Generate a semantic title from the user's first message.

    Uses the ``cheap`` role (lightweight model) via RoleRouter, falling back
    to legacy config if no role is configured.
    """
    try:
        from suzent.core.role_router import get_role_router
        from suzent.database import generate_chat_title, get_database

        title_source = _clean_title_source(user_content)
        if not title_source:
            logger.warning(f"Auto-title skipped for {chat_id}: no user text")
            return None

        router = get_role_router()
        model = router.get_model_id("cheap")
        logger.info(
            f"[AutoTitle] cheap role model={model!r}, fallback={fallback_model!r}"
        )

        candidate_models: list[str] = []
        for candidate in (model, fallback_model):
            if candidate and candidate not in candidate_models:
                candidate_models.append(candidate)

        if not candidate_models:
            # An ACP-only install has no native model to ask. Falling through to
            # the heuristic below still beats leaving the chat named "New Chat".
            logger.info(f"Auto-title for {chat_id}: no model configured")

        for candidate_model in candidate_models:
            try:
                title = await _generate_title_with_model(candidate_model, title_source)
            except Exception as e:
                logger.warning(
                    f"Auto-title model failed for {chat_id} "
                    f"(model={candidate_model!r}): {e}"
                )
                continue

            if not title:
                logger.warning(
                    f"Auto-title model returned empty title for {chat_id} "
                    f"(model={candidate_model!r})"
                )
                continue

            db = get_database()
            if not db.update_chat(chat_id, title=title):
                logger.warning(f"Auto-title update failed for missing chat {chat_id}")
                return None

            logger.info(
                f"Auto-title set for {chat_id} using model={candidate_model!r} "
                f"(selected={model!r}, fallback={fallback_model!r}): {title!r}"
            )
            return title

        title = generate_chat_title(title_source)
        if title == "New Chat":
            logger.warning(f"Auto-title fallback skipped for {chat_id}: no user text")
            return None

        db = get_database()
        if not db.update_chat(chat_id, title=title):
            logger.warning(
                f"Auto-title fallback update failed for missing chat {chat_id}"
            )
            return None

        logger.info(f"Auto-title fallback set for {chat_id}: {title!r}")
        return title
    except Exception as e:
        logger.warning(f"Auto-title generation failed for {chat_id}: {e}")
    return None
