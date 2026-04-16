"""
Context injection module — builds AgentDeps for pydantic-ai tool functions.

With pydantic-ai, per-tool context injection (set_context, set_chat_context)
is replaced by a single AgentDeps object passed via RunContext to every tool.
This module constructs that object from the chat configuration.
"""

import asyncio
from typing import Optional, Any

from suzent.core.agent_deps import AgentDeps
from suzent.config import CONFIG, get_effective_volumes
from suzent.logger import get_logger

logger = get_logger(__name__)


def _get_config_value(config: Optional[dict], key: str, default: Any) -> Any:
    """Get a config value with fallback to default if config is None or key missing."""
    if config is None:
        return default
    return config.get(key, default)


def build_agent_deps(
    chat_id: str,
    user_id: str = None,
    config: Optional[dict] = None,
) -> AgentDeps:
    """
    Build an AgentDeps instance from chat configuration.

    This replaces the old inject_chat_context() function. Instead of mutating
    tool instances, we build a single dependency object that pydantic-ai
    injects into all tool functions via RunContext[AgentDeps].

    Args:
        chat_id: The chat session identifier.
        user_id: The user identifier (defaults to CONFIG.user_id).
        config: Optional per-chat configuration dict.

    Returns:
        AgentDeps instance ready to be passed to agent.run().
    """
    if user_id is None:
        user_id = CONFIG.user_id

    sandbox_enabled = _get_config_value(
        config, "sandbox_enabled", CONFIG.sandbox_enabled
    )
    workspace_root = _get_config_value(config, "workspace_root", CONFIG.workspace_root)
    cwd = _get_config_value(config, "cwd", None)
    auto_approve_tools = _get_config_value(config, "auto_approve_tools", False)
    tool_permission_policies = _get_config_value(
        config, "permission_policies", CONFIG.permission_policies
    )
    custom_volumes = get_effective_volumes(
        _get_config_value(config, "sandbox_volumes", None)
    )

    # Build PathResolver
    from suzent.tools.filesystem.path_resolver import PathResolver

    path_resolver = PathResolver(
        chat_id,
        sandbox_enabled,
        sandbox_data_path=CONFIG.sandbox_data_path,
        custom_volumes=custom_volumes,
        workspace_root=workspace_root,
    )

    # Memory manager
    from suzent.memory.lifecycle import get_memory_manager

    memory_manager = get_memory_manager()

    # Social context
    runtime = _get_config_value(config, "_runtime", {})
    social_ctx = _get_config_value(config, "social_context", {})
    channel_manager = runtime.get("channel_manager") if runtime else None
    event_loop = runtime.get("event_loop") if runtime else None

    # Desktop mode fallback for social
    if not channel_manager:
        try:
            from suzent.core.social_brain import get_active_social_brain

            brain = get_active_social_brain()
            if brain:
                channel_manager = brain.channel_manager
                try:
                    event_loop = asyncio.get_running_loop()
                except RuntimeError:
                    event_loop = None
        except Exception:
            pass

    # Skill manager
    from suzent.skills import get_skill_manager

    skill_manager = get_skill_manager()

    tool_approval_policy = _get_config_value(config, "tool_approval_policy", {})

    # SECURITY: Make a defensive copy to prevent accidental mutation of shared config
    # This ensures each AgentDeps instance has its own independent policy dict
    assert isinstance(tool_approval_policy, dict), "tool_approval_policy must be a dict"
    tool_approval_policy = dict(tool_approval_policy)

    return AgentDeps(
        chat_id=chat_id,
        user_id=user_id,
        sandbox_enabled=sandbox_enabled,
        workspace_root=workspace_root,
        cwd=cwd,
        custom_volumes=custom_volumes,
        path_resolver=path_resolver,
        memory_manager=memory_manager,
        channel_manager=channel_manager,
        event_loop=event_loop,
        social_context=social_ctx,
        skill_manager=skill_manager,
        auto_approve_tools=auto_approve_tools,
        tool_permission_policies=dict(tool_permission_policies or {}),
        tool_approval_policy=tool_approval_policy,
        a2ui_queue=asyncio.Queue(),
        inline_a2ui_surfaces={},
    )
