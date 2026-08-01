"""Tool registry module for pydantic-ai.

Auto-builds the tool registry from Tool subclasses. Each Tool class's
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
from suzent.tools.base import ToolResult, truncate_tool_output

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Factory: Tool class → pydantic-ai function / PydanticTool
# ---------------------------------------------------------------------------


def _make_tool(
    tool_cls, *, defer_loading: bool = False
) -> Union[Callable, PydanticTool]:
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

    limit = tool_cls.output_char_limit
    keep_tail = tool_cls.keep_output_tail

    if asyncio.iscoroutinefunction(original):

        @functools.wraps(original)
        async def wrapper(*args, **kwargs):
            result = await tool_cls().forward(*args, **kwargs)
            if isinstance(result, ToolResult):
                result.message = truncate_tool_output(
                    result.message, limit, keep_tail=keep_tail
                )
            return result

    else:

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            result = tool_cls().forward(*args, **kwargs)
            if isinstance(result, ToolResult):
                result.message = truncate_tool_output(
                    result.message, limit, keep_tail=keep_tail
                )
            return result

    wrapper.__name__ = tool_cls.tool_name

    if tool_cls.requires_approval or defer_loading:
        prepare = None
        if defer_loading:

            async def prepare(ctx, tool_definition):
                from suzent.agent_manager import get_suppressed_tools

                policy = getattr(ctx.deps, "tool_approval_policy", {}) or {}
                denied = (
                    policy.get(tool_cls.name) == "always_deny"
                    or policy.get(tool_cls.tool_name) == "always_deny"
                )
                suppressed = (
                    tool_cls.name in get_suppressed_tools(ctx.deps.chat_id)
                    and tool_cls.name not in ctx.deps.base_tool_names
                )
                return None if denied or suppressed else tool_definition

        return PydanticTool(
            wrapper,
            requires_approval=tool_cls.requires_approval,
            defer_loading=defer_loading,
            prepare=prepare,
        )

    return wrapper


# ---------------------------------------------------------------------------
# Tool class imports (lazy, collected once)
# ---------------------------------------------------------------------------

_REGISTRY: Optional[Dict[str, Union[Callable, PydanticTool]]] = None


def _all_tool_classes() -> list:
    """Import and return all tool classes in display order."""
    from suzent.tools.filesystem import (
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        GlobTool,
        GrepTool,
    )
    from suzent.tools.shell.shell_tools import (
        CheckCommandTool,
        RunCommandTool,
        StartCommandTool,
        StopCommandTool,
    )
    from suzent.tools.webpage_tool import WebpageTool
    from suzent.tools.websearch_tool import WebSearchTool
    from suzent.tools.goal_tool import GoalTool
    from suzent.tools.task_create_tool import TaskCreateTool
    from suzent.tools.task_update_tool import TaskUpdateTool
    from suzent.tools.task_list_tool import TaskListTool
    from suzent.tools.browsing_tool import BrowsingTool
    from suzent.tools.skill_tool import SkillTool
    from suzent.tools.social_message_tool import SocialMessageTool
    from suzent.tools.voice_tool import SpeakTool
    from suzent.tools.image_generation_tool import ImageGenerationTool
    from suzent.tools.image_vision_tool import ImageVisionTool
    from suzent.tools.memory_tools import MemorySearchTool
    from suzent.tools.session_search_tool import SessionSearchTool
    from suzent.tools.render_ui_tool import RenderUITool
    from suzent.tools.ask_question_tool import AskQuestionTool
    from suzent.tools.agent_tool import AgentTool

    return [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        GlobTool,
        GrepTool,
        RunCommandTool,
        StartCommandTool,
        CheckCommandTool,
        StopCommandTool,
        BrowsingTool,
        WebpageTool,
        WebSearchTool,
        AskQuestionTool,
        GoalTool,
        TaskCreateTool,
        TaskUpdateTool,
        TaskListTool,
        RenderUITool,
        ImageGenerationTool,
        ImageVisionTool,
        SpeakTool,
        SocialMessageTool,
        SkillTool,
        MemorySearchTool,
        SessionSearchTool,
        AgentTool,
    ]


def migrate_shell_tool_names(tool_names: List[str]) -> List[str]:
    """Migrate legacy shell selections to the unified ShellTool capability."""
    legacy_names = {"BashTool", "ProcessTool", "bash_execute", "process_manage"}
    migrated = ["ShellTool" if name in legacy_names else name for name in tool_names]
    return list(dict.fromkeys(migrated))


def expand_tool_dependencies(tool_names: List[str]) -> List[str]:
    """Expand logical tool selections into the runtime tools they require.

    ShellTool is the user-facing selection. Its three companion operations are
    registered in the same capability without separate UI toggles.
    """
    expanded = migrate_shell_tool_names(tool_names)
    companions = ["StartCommandTool", "CheckCommandTool", "StopCommandTool"]
    if "ShellTool" in expanded:
        index = expanded.index("ShellTool") + 1
        for companion in companions:
            if companion not in expanded:
                expanded.insert(index, companion)
                index += 1
    return expanded


def get_tool_groups() -> List[Dict]:
    """Derive UI tool groups from each tool's ``group`` class attribute."""
    groups: Dict[str, List[str]] = {}
    for cls in _all_tool_classes():
        g = getattr(cls, "group", "")
        if not g:
            continue
        groups.setdefault(g, []).append(cls.name)
    return [{"label": label, "tools": tools} for label, tools in groups.items()]


def _build_registry() -> Dict[str, Union[Callable, PydanticTool]]:
    """Import all Tool classes and build the registry."""
    registry: Dict[str, Union[Callable, PydanticTool]] = {}
    for cls in _all_tool_classes():
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


def get_deferred_tool_functions(exclude: set[str]) -> list[PydanticTool]:
    """Build fresh deferred tools for Pydantic AI's native ToolSearch capability."""
    tools: list[PydanticTool] = []
    for cls in _all_tool_classes():
        if cls.name in exclude or not getattr(cls, "deferrable", True):
            continue
        try:
            tool = _make_tool(cls, defer_loading=True)
        except Exception as exc:
            logger.error(f"Failed to register deferred tool {cls.name}: {exc}")
            continue
        if isinstance(tool, PydanticTool):
            tools.append(tool)
    return tools


def get_tool_class_name(runtime_name: str) -> Optional[str]:
    """Resolve a model-facing function name to its Suzent tool class name."""
    for cls in _all_tool_classes():
        if cls.tool_name == runtime_name:
            return cls.name
    return None


def get_tool_runtime_name(class_name: str) -> Optional[str]:
    """Resolve a Suzent tool class name to its model-facing function name."""
    for cls in _all_tool_classes():
        if cls.name == class_name:
            return cls.tool_name
    return None


def list_available_tools() -> List[str]:
    """List all available tool names (class-name style)."""
    return sorted(_get_registry().keys())


def get_tool_registry() -> Dict[str, Union[Callable, PydanticTool]]:
    """Get a copy of the full tool function registry."""
    return _get_registry().copy()


def get_tool_session_guidance_entries(tool_names: List[str]) -> List[Dict[str, object]]:
    """Collect deduplicated session guidance entries from selected tools.

    Each entry includes the tool name, priority, and guidance text. Entries are
    sorted by each tool class's ``guidance_priority`` value.
    """
    classes_by_name = {cls.name: cls for cls in _all_tool_classes()}
    collected: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    for name in tool_names:
        cls = classes_by_name.get(name)
        if cls is None:
            continue

        guidance = getattr(cls, "session_guidance", None)
        if not guidance or guidance in seen:
            continue

        seen.add(guidance)
        collected.append((getattr(cls, "guidance_priority", 100), cls.name, guidance))

    collected.sort(key=lambda item: (item[0], item[1]))
    return [
        {"priority": priority, "tool_name": tool_name, "guidance": guidance}
        for priority, tool_name, guidance in collected
    ]


def get_tool_session_guidance(tool_names: List[str]) -> List[str]:
    """Collect deduplicated session guidance text from selected tools."""
    return [
        entry["guidance"] for entry in get_tool_session_guidance_entries(tool_names)
    ]
