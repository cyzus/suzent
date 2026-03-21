"""
Tool registry module for pydantic-ai.

Auto-builds the tool registry from Tool subclasses.  Each Tool class's
``forward()`` method is wrapped as a pydantic-ai compatible function.
Tools with ``requires_approval = True`` are wrapped in ``pydantic_ai.Tool``
with native deferred-tool approval.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Callable, Dict, List, Optional, Union

from pydantic_ai import Tool as PydanticTool

from suzent.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Factory: Tool class → pydantic-ai function / PydanticTool
# ---------------------------------------------------------------------------


def _make_tool(tool_cls) -> Union[Callable, PydanticTool]:
    """Create a pydantic-ai tool from a suzent Tool class.

    * Creates a wrapper that instantiates a fresh Tool per call (thread-safe).
    * ``functools.wraps`` copies ``__wrapped__`` so ``inspect.signature``
      returns the original ``forward()`` parameter types – pydantic-ai uses
      these for JSON schema generation.
    * ``wrapper.__name__`` is set to ``tool_cls.tool_name`` so pydantic-ai
      uses a descriptive name (e.g. "read_file") instead of "forward".
    * If the tool requires approval, returns a ``PydanticTool`` with
      ``requires_approval=True`` (pydantic-ai native deferred-tool support).
    """
    template = tool_cls()
    original = template.forward

    if asyncio.iscoroutinefunction(original):

        @functools.wraps(original)
        async def wrapper(*args, **kwargs):
            return await tool_cls().forward(*args, **kwargs)

    else:

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            return tool_cls().forward(*args, **kwargs)

    wrapper.__name__ = tool_cls.tool_name

    if tool_cls.requires_approval:
        return PydanticTool(wrapper, requires_approval=True)

    return wrapper


# ---------------------------------------------------------------------------
# Tool class imports (lazy, collected once)
# ---------------------------------------------------------------------------

_REGISTRY: Optional[Dict[str, Union[Callable, PydanticTool]]] = None


def _build_registry() -> Dict[str, Union[Callable, PydanticTool]]:
    """Import all Tool classes and build the registry."""

    from suzent.tools.websearch_tool import WebSearchTool
    from suzent.tools.webpage_tool import WebpageTool
    from suzent.tools.bash_tool import BashTool
    from suzent.tools.process_tool import ProcessTool
    from suzent.tools.read_file_tool import ReadFileTool
    from suzent.tools.write_file_tool import WriteFileTool
    from suzent.tools.edit_file_tool import EditFileTool
    from suzent.tools.glob_tool import GlobTool
    from suzent.tools.grep_tool import GrepTool
    from suzent.tools.planning_tool import PlanningTool
    from suzent.tools.browsing_tool import BrowsingTool
    from suzent.tools.skill_tool import SkillTool
    from suzent.tools.social_message_tool import SocialMessageTool
    from suzent.tools.voice_tool import SpeakTool
    from suzent.tools.image_generation_tool import ImageGenerationTool
    from suzent.memory.tools import MemorySearchTool, MemoryBlockUpdateTool
    from suzent.tools.render_ui_tool import RenderUITool

    ALL_TOOLS = [
        WebSearchTool,
        WebpageTool,
        BashTool,
        ProcessTool,
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        GlobTool,
        GrepTool,
        PlanningTool,
        BrowsingTool,
        SkillTool,
        SocialMessageTool,
        SpeakTool,
        ImageGenerationTool,
        MemorySearchTool,
        MemoryBlockUpdateTool,
        RenderUITool,
    ]

    registry: Dict[str, Union[Callable, PydanticTool]] = {}
    for cls in ALL_TOOLS:
        try:
            registry[cls.name] = _make_tool(cls)
        except Exception as e:
            logger.error(f"Failed to register tool {cls.name}: {e}")

    return registry


def _get_registry() -> Dict[str, Union[Callable, PydanticTool]]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


# ---------------------------------------------------------------------------
# Public API (unchanged from before – agent_manager.py keeps working)
# ---------------------------------------------------------------------------


def get_tool_function(tool_name: str) -> Optional[Union[Callable, PydanticTool]]:
    """Get a tool function by its class name (e.g. "ReadFileTool").

    Returns a plain function or ``pydantic_ai.Tool`` object, both valid
    for ``Agent(tools=[...])``.
    """
    registry = _get_registry()
    fn = registry.get(tool_name)
    if fn is None:
        logger.warning(f"Tool function not found: {tool_name}")
    return fn


def list_available_tools() -> List[str]:
    """List all available tool names (class-name style)."""
    return sorted(_get_registry().keys())


def get_tool_registry() -> Dict[str, Union[Callable, PydanticTool]]:
    """Get a copy of the full tool function registry."""
    return _get_registry().copy()
