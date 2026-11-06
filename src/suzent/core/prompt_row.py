"""The transcript row for a prompt a person sent, written before its turn runs.

Every surface a person types into -- the desktop, mobile, voice, an ACP client,
a chat app -- writes that row here, before the stream opens, so the chat window
shows the prompt while the turn is still running. Turns the system starts (cron,
heartbeat, another agent) have no such row; they announce a trigger instead.
"""

from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

_MAX_NAME_LENGTH = 100


def display_name(value: Any, fallback: str) -> str:
    """A sender's name as the transcript may show it, or ``fallback``.

    The name comes from another program and is rendered beside the prompt, so
    anything that is not a short printable string is replaced, not shown.
    """
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _MAX_NAME_LENGTH
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        return fallback
    return value.strip()


def sanitized_prompt(message: str) -> str:
    """Neutralize forged reminder delimiters before anything records the message.

    The pre-written display row and the row the ACP turn later reconciles
    against have to be the same string. Sanitizing only inside the turn left the
    raw text in the pre-written row and appended a second, escaped copy beside
    it. Doing it here means both see one value; the turn's own pass is then a
    no-op, since escaping is idempotent.
    """
    from suzent.core.system_reminder import sanitize_untrusted_text

    return sanitize_untrusted_text(message) if message else message


def prewrite_prompt(
    chat_id: str,
    message: str,
    files: list | None = None,
    *,
    client_message_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> tuple[str, bool | None]:
    """Write the prompt's row and return the message the turn should run.

    The second value is whether the row is really in the transcript: ``None``
    when ``client_message_id`` names a row that is already there.
    """
    message = sanitized_prompt(message)
    return message, _write_row(chat_id, message, files, client_message_id, metadata)


def _write_row(
    chat_id: str,
    message: str,
    files: list | None,
    client_message_id: str | None,
    metadata: dict[str, str] | None,
) -> bool | None:
    """Append the row, reporting whether it was stored.

    The turn uses this as its licence to recognize the row and not write it
    again, and a write that failed leaves the previous turn's row in that
    position -- which the same prompt sent again matches exactly. Believing the
    prewrite then loses the message.
    """
    # Here, not at the top: the ACP server process imports this module for
    # display_name and never opens the database.
    from suzent.database import get_database

    if not chat_id:
        return False

    content = (message or "").strip()
    file_rows = [f for f in files or [] if isinstance(f, dict)]
    if not content and not file_rows:
        return False

    entry: dict = {"role": "user", "content": content}
    if file_rows:
        entry["files"] = file_rows
    if metadata:
        entry["metadata"] = metadata

    try:
        if client_message_id is not None:
            status = get_database().append_chat_message_once(
                chat_id, entry, client_message_id
            )
            if status == "duplicate":
                return None
            return status == "created"
        return bool(get_database().append_chat_message(chat_id, entry))
    except Exception as exc:
        # The type only. A database error carries its statement's bound
        # parameters, which here are the user's prompt and their attachments'
        # names -- exactly what must not reach a log.
        logger.debug(
            f"Failed to prewrite user display message for {chat_id}: "
            f"{type(exc).__name__}"
        )
        return False
