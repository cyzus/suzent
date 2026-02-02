"""
Context injection module for configuring agent tools with chat context.

This module handles:
- Injecting chat and user context into tools
- Creating PathResolver instances for file tools
- Configuration value resolution with fallbacks
"""

from typing import Optional, Any

from smolagents import CodeAgent

from suzent.config import CONFIG, get_effective_volumes
from suzent.logger import get_logger

logger = get_logger(__name__)


def _get_config_value(config: Optional[dict], key: str, default: Any) -> Any:
    """Get a config value with fallback to default if config is None or key missing."""
    if config is None:
        return default
    return config.get(key, default)


def _create_path_resolver(chat_id: str, config: Optional[dict]) -> Any:
    """
    Create a PathResolver instance with configuration overrides.

    Args:
        chat_id: Chat session ID
        config: Optional chat configuration overriding globals

    Returns:
        PathResolver instance
    """
    from suzent.tools.path_resolver import PathResolver

    sandbox_enabled = _get_config_value(
        config, "sandbox_enabled", CONFIG.sandbox_enabled
    )
    workspace_root = _get_config_value(config, "workspace_root", CONFIG.workspace_root)
    custom_volumes = get_effective_volumes(
        _get_config_value(config, "sandbox_volumes", None)
    )

    return PathResolver(
        chat_id,
        sandbox_enabled,
        sandbox_data_path=CONFIG.sandbox_data_path,
        custom_volumes=custom_volumes,
        workspace_root=workspace_root,
    )


def inject_chat_context(
    agent: CodeAgent, chat_id: str, user_id: str = None, config: dict = None
) -> None:
    """
    Inject chat context into agent tools that support it.

    Args:
        agent: The agent instance whose tools should receive context.
        chat_id: The chat identifier to inject into tools.
        user_id: The user identifier for memory system (defaults to CONFIG.user_id).
        config: Optional chat configuration dict containing per-chat settings.
    """
    if not chat_id or not hasattr(agent, "_tool_instances"):
        return

    # Use configured user_id if not provided
    if user_id is None:
        user_id = CONFIG.user_id

    # Get effective configuration values
    sandbox_enabled = _get_config_value(
        config, "sandbox_enabled", CONFIG.sandbox_enabled
    )
    workspace_root = _get_config_value(config, "workspace_root", CONFIG.workspace_root)

    # Tool name sets for efficient lookup
    memory_tool_names = {"MemorySearchTool", "MemoryBlockUpdateTool"}
    file_tool_names = {
        "ReadFileTool",
        "WriteFileTool",
        "EditFileTool",
        "GlobTool",
        "GrepTool",
    }

    # --- Tool Context Injection ---
    for tool_instance in agent._tool_instances:
        tool_name = tool_instance.__class__.__name__

        # Inject chat_id for tools like PlanningTool
        if hasattr(tool_instance, "set_chat_context"):
            tool_instance.set_chat_context(chat_id)

        # Inject user_id and chat_id for memory tools
        if tool_name in memory_tool_names:
            if hasattr(tool_instance, "set_context"):
                tool_instance.set_context(chat_id=chat_id, user_id=user_id)

        # Configure BashTool with mode and context
        elif tool_name == "BashTool":
            tool_instance.chat_id = chat_id
            tool_instance.sandbox_enabled = sandbox_enabled
            tool_instance.workspace_root = workspace_root

            # Inject per-chat sandbox volumes if configured
            volumes = get_effective_volumes(
                _get_config_value(config, "sandbox_volumes", None)
            )
            tool_instance.custom_volumes = volumes

            if sandbox_enabled and hasattr(tool_instance, "set_custom_volumes"):
                tool_instance.set_custom_volumes(volumes)

            logger.debug(
                f"BashTool configured: sandbox={sandbox_enabled}, workspace={workspace_root}"
            )

        # Inject PathResolver into file tools
        elif tool_name in file_tool_names:
            if hasattr(tool_instance, "set_context"):
                resolver = _create_path_resolver(chat_id, config)
                tool_instance.set_context(resolver)
