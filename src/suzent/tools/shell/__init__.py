"""Unified shell capability lifecycle helpers."""

from suzent.logger import get_logger

logger = get_logger(__name__)


def cleanup_shell_session(chat_id: str) -> None:
    """Stop host and sandbox processes associated with a deleted chat."""
    from suzent.sandbox import SandboxManager
    from suzent.tools.shell.host_process_registry import HostProcessRegistry

    try:
        HostProcessRegistry().evict_chat(chat_id)
    except Exception as exc:
        logger.warning(f"Failed to clean up host processes for {chat_id}: {exc}")

    SandboxManager.remove_session_from_all_managers(chat_id)


__all__ = ["cleanup_shell_session"]
