"""
Retry checkpoint management (context-only rewind).

Before each agent turn we snapshot:
  - agent_state (bytes) — message history before the user's message
  - chat.messages       — display messages before the user's message
  - the user message text + file metadata + config snapshot

Rewind / retry strictly restores conversation history and agent context;
local filesystem changes are intentionally left untouched.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)


def save_retry_checkpoint(
    chat_id: str,
    agent_state_before: Optional[bytes],
    messages_before: list,
    user_message: str,
    user_files: list,
    config_snapshot: dict,
    turn_input: dict[str, Any] | None = None,
) -> str | None:
    """
    Persist a retry checkpoint for *chat_id* in its chat log.

    Called at the very start of process_turn(), before any state is mutated.
    Replaces any previously stored checkpoint for this chat.
    """
    try:
        from suzent.database import get_database

        checkpoint_id = uuid.uuid4().hex
        saved = get_database().save_retry_checkpoint(
            chat_id,
            checkpoint_id=checkpoint_id,
            agent_state_before=agent_state_before,
            messages_before=list(messages_before),
            user_message=user_message,
            user_files=list(user_files),
            config_snapshot={
                **{
                    key: value
                    for key, value in config_snapshot.items()
                    if not key.startswith("_retry_")
                },
                "_retry_checkpoint_id": checkpoint_id,
                "_retry_input": turn_input or {},
            },
        )
        if not saved:
            return None

        logger.debug(f"[retry] checkpoint saved for {chat_id}")
        return checkpoint_id

    except Exception as e:
        logger.error(f"[retry] save_retry_checkpoint failed for {chat_id}: {e}")
        return None


def record_retry_checkpoint_revision(
    chat_id: str, checkpoint_id: str, revision: int
) -> None:
    """Bind a checkpoint to its own completed turn, never a later autonomous turn."""
    from suzent.database import get_database

    db = get_database()
    checkpoint = db.get_retry_checkpoint(chat_id)
    if checkpoint is None or checkpoint.id != checkpoint_id:
        return
    db.update_retry_checkpoint(
        chat_id,
        checkpoint_id,
        {
            "config_snapshot": {
                **checkpoint.config_snapshot,
                "_retry_revision": revision,
            }
        },
    )


def load_retry_checkpoint(chat_id: str) -> Optional[Any]:
    """Return the chat's ``RetryCheckpoint``, or None."""
    try:
        from suzent.database import get_database

        return get_database().get_retry_checkpoint(chat_id)
    except Exception as e:
        logger.error(f"[retry] load_retry_checkpoint failed for {chat_id}: {e}")
        return None


def apply_retry_checkpoint(
    chat_id: str, expected_revision: int | None = None
) -> Optional[dict]:
    """
    Restore agent state and display messages to the checkpoint state (context-only).

    Returns ``{"user_message": ..., "user_files": ..., "config_snapshot": ...}``
    so the caller can re-run process_turn() with the original inputs, or None
    if no checkpoint is found.
    """
    from suzent.database import get_database

    checkpoint = load_retry_checkpoint(chat_id)
    if checkpoint is None:
        logger.warning(f"[retry] No checkpoint found for chat {chat_id}")
        return None

    try:
        db = get_database()

        # Restore agent state + display messages in DB. rewrite_chat_messages keeps the
        # sidebar summary and FTS index in sync with the restored message list.
        if (
            expected_revision is not None
            and checkpoint.config_snapshot.get("_retry_revision") != expected_revision
        ):
            return None
        if not db.rewrite_chat_messages(
            chat_id,
            list(checkpoint.messages_before),
            agent_state=checkpoint.agent_state_before,
            expected_revision=expected_revision,
        ):
            return None

        return {
            "user_message": checkpoint.user_message,
            "user_files": list(checkpoint.user_files),
            "turn_input": checkpoint.config_snapshot.get("_retry_input", {}),
            "config_snapshot": {
                key: value
                for key, value in checkpoint.config_snapshot.items()
                if not key.startswith("_retry_")
            },
        }

    except Exception as e:
        logger.error(f"[retry] apply_retry_checkpoint failed for {chat_id}: {e}")
        return None
