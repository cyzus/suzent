"""Auto-title generation for new chats using the RoleRouter."""

from loguru import logger


async def generate_auto_title(
    chat_id: str, user_content: str, fallback_model: str | None = None
) -> str | None:
    """Generate a semantic title from the user's first message.

    Uses the ``cheap`` role (lightweight model) via RoleRouter, falling back
    to legacy config if no role is configured.
    """
    try:
        from suzent.llm import LLMClient
        from suzent.core.role_router import get_role_router
        from suzent.database import get_database

        router = get_role_router()
        model = router.get_model_id("cheap")

        if not model:
            # Legacy fallback
            from suzent.core.providers.helpers import get_effective_memory_config
            from suzent.config import CONFIG

            mem_config = get_effective_memory_config()
            model = mem_config.get("extraction_model") or fallback_model or CONFIG.model

        if not model:
            logger.warning(f"Auto-title skipped for {chat_id}: no model configured")
            return None

        client = LLMClient(model=model)
        title = await client.complete(
            prompt=user_content[:500],
            system=(
                "Generate a short title (3-6 words, no punctuation, no quotes) "
                "that captures what this message is about. Reply with only the title."
            ),
            temperature=0.3,
            max_tokens=20,
        )
        title = title.strip().strip("\"'").strip()
        if title:
            db = get_database()
            db.update_chat(chat_id, title=title)
            logger.info(f"Auto-title set for {chat_id}: {title!r}")
            return title
    except Exception as e:
        logger.warning(f"Auto-title generation failed for {chat_id}: {e}")
    return None
