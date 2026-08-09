"""Tool registry module for pydantic-ai.

Auto-builds the tool registry from Tool subclasses. Each Tool class's
``forward()`` method is wrapped as a pydantic-ai compatible function.
Tools with ``requires_approval = True`` are wrapped in ``pydantic_ai.Tool``
with native deferred-tool approval.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import re
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
    from suzent.tools.agent_lifecycle_tools import (
        AgentListTool,
        AgentReadTool,
        AgentStopTool,
        AgentWaitTool,
    )

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
        AgentListTool,
        AgentReadTool,
        AgentWaitTool,
        AgentStopTool,
    ]


SHELL_TOOL_CLASS_NAMES = (
    "RunCommandTool",
    "StartCommandTool",
    "CheckCommandTool",
    "StopCommandTool",
)

AGENT_LIFECYCLE_TOOL_NAMES = (
    "AgentListTool",
    "AgentReadTool",
    "AgentWaitTool",
    "AgentStopTool",
)

LEGACY_SHELL_TOOL_NAMES = {
    "ShellTool",
    "BashTool",
    "ProcessTool",
    "bash_execute",
    "process_manage",
}

CAPABILITY_DESCRIPTIONS = {
    "Filesystem": "Read, search, create, and modify files in the configured workspace.",
    "Shell": "Run bounded commands and control long-running background processes.",
    "Web": "Search the web, retrieve pages, and interact with browser-based content.",
    "Agent": "Plan work, ask questions, render interfaces, and delegate bounded tasks.",
    "Creative": "Generate, inspect, speak, or share rich media and social content.",
    "Memory & recall": "Search durable memory and retrieve relevant past sessions.",
}

TOOL_DESCRIPTION_OVERRIDES = {
    "BrowsingTool": "Open and interact with browser pages, including navigation, clicks, forms, and screenshots.",
    "AskQuestionTool": "Pause execution to ask the user a focused question when their input is required.",
    "GoalTool": "Create, inspect, and complete a durable goal that can continue across agent turns.",
    "TaskCreateTool": "Create structured project tasks with dependencies, assignees, and progress metadata.",
    "TaskUpdateTool": "Update the status, ownership, description, or dependencies of an existing task.",
    "TaskListTool": "List project tasks and their current status, ownership, and dependency relationships.",
    "AgentListTool": "List active or recent sub-agent tasks owned by the current conversation.",
    "AgentReadTool": "Read a sub-agent task's status and visible conversation transcript.",
    "AgentWaitTool": "Wait for one of up to eight selected sub-agent tasks to finish.",
    "AgentStopTool": "Stop a running sub-agent task owned by the current conversation.",
    "RenderUITool": "Render an interactive interface such as a form, table, card, or action panel.",
    "SpeakTool": "Convert a response to speech and return playable audio to the conversation.",
    "SocialMessageTool": "Send a message through a configured social channel after approval.",
}


def migrate_shell_tool_names(tool_names: List[str]) -> List[str]:
    """Expand legacy aggregate shell selections into independently selectable tools."""
    migrated: list[str] = []
    for name in tool_names:
        if name in LEGACY_SHELL_TOOL_NAMES:
            migrated.extend(SHELL_TOOL_CLASS_NAMES)
        else:
            migrated.append(name)
    return list(dict.fromkeys(migrated))


def expand_tool_dependencies(tool_names: List[str]) -> List[str]:
    """Normalize legacy aggregate selections while preserving modern choices."""
    expanded = migrate_shell_tool_names(tool_names)
    if "AgentTool" in expanded:
        expanded.extend(AGENT_LIFECYCLE_TOOL_NAMES)
    return list(dict.fromkeys(expanded))


def _humanize_tool_name(name: str) -> str:
    without_suffix = re.sub(r"Tool$", "", name)
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", without_suffix)


def _tool_description(cls: type) -> str:
    explicit = getattr(cls, "description", None)
    if explicit:
        return str(explicit)
    if cls.name in TOOL_DESCRIPTION_OVERRIDES:
        return TOOL_DESCRIPTION_OVERRIDES[cls.name]
    documentation = cls.__dict__.get("__doc__") or inspect.getdoc(cls.forward) or ""
    paragraph = documentation.split("\n\n", 1)[0].replace("\n", " ").strip()
    return paragraph or f"Use the {_humanize_tool_name(cls.name).lower()} tool."


def get_tool_capabilities() -> List[Dict[str, object]]:
    """Return the user-facing capability catalog with rich tool metadata."""
    capabilities: Dict[str, list[dict[str, object]]] = {}
    for cls in _all_tool_classes():
        capability = getattr(cls, "group", "")
        if not capability:
            continue
        label = str(capability.value if hasattr(capability, "value") else capability)
        capabilities.setdefault(label, []).append(
            {
                "id": cls.name,
                "name": getattr(cls, "display_name", None)
                or _humanize_tool_name(cls.name),
                "description": _tool_description(cls),
                "runtimeName": cls.tool_name,
                "requiresApproval": bool(cls.requires_approval),
            }
        )
    return [
        {
            "id": re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"),
            "label": label,
            "description": CAPABILITY_DESCRIPTIONS.get(label, ""),
            "tools": tools,
        }
        for label, tools in capabilities.items()
    ]


def group_tools_by_capability(tool_names: List[str]) -> Dict[str, List[str]]:
    """Group selected registry keys by their owning capability ID."""
    selected = set(tool_names)
    grouped: Dict[str, List[str]] = {}
    for capability in get_tool_capabilities():
        capability_tools = [
            tool["id"] for tool in capability["tools"] if tool["id"] in selected
        ]
        if capability_tools:
            grouped[str(capability["id"])] = capability_tools
    return grouped


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


def list_configurable_tools() -> List[str]:
    """List user-facing tool toggles, excluding capability implementation tools."""
    return sorted(cls.name for cls in _all_tool_classes() if getattr(cls, "group", ""))


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
