"""
Tool registry module for pydantic-ai function-based tools.

Provides:
- A mapping of tool names → tool functions for pydantic-ai Agent registration
- list_available_tools() for config UI compatibility
- get_tool_function() for dynamic tool lookup
"""

from typing import Callable, Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)


def _get_tool_functions() -> Dict[str, Callable]:
    """Import and return the tool function registry (lazy)."""
    from suzent.tools.tool_functions import TOOL_FUNCTIONS

    return TOOL_FUNCTIONS


def get_tool_function(tool_name: str) -> Optional[Callable]:
    """
    Get a tool function by its class name.

    Args:
        tool_name: The tool name (e.g., "WebSearchTool").

    Returns:
        The tool function, or None if not found.
    """
    registry = _get_tool_functions()
    fn = registry.get(tool_name)
    if fn is None:
        logger.warning(f"Tool function not found: {tool_name}")
    return fn


def list_available_tools() -> List[str]:
    """
    List all available tool names.

    Returns:
        Sorted list of tool names (class-name style, e.g. "WebSearchTool").
    """
    return sorted(_get_tool_functions().keys())


def get_tool_registry() -> Dict[str, Callable]:
    """
    Get a copy of the full tool function registry.

    Returns:
        Dict mapping tool names to their function objects.
    """
    return _get_tool_functions().copy()
