"""Auto-title generation for new chats using the extraction_model."""

from loguru import logger


async def generate_auto_title(
    chat_id: str, user_content: str, fallback_model: str | None = None
) -> str | None:
    """Generate a semantic title from the user's first message.

    Uses extraction_model (lightweight) and runs in parallel with the agent.
    Updates the DB and returns the title string, or None on failure.
    """
    try:
        from suzent.llm import LLMClient
        from suzent.core.providers.helpers import get_effective_memory_config
        from suzent.database import get_database

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
