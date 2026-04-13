"""
Agent management module for creating and managing pydantic-ai agents.

This module handles the lifecycle of AI agents including:
- Creating pydantic-ai Agent instances with specified configurations
- Managing MCP server toolsets
- Managing global agent instances
"""

import asyncio
import os
from typing import Optional, Dict, Any, List

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio, MCPServerStreamableHTTP
from pydantic_ai.tools import DeferredToolRequests

from suzent.core.agent_deps import AgentDeps
from suzent.core.model_factory import create_pydantic_ai_model
from suzent.core.providers import get_enabled_models_from_db

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.prompts import (
    STATIC_INSTRUCTIONS,
    register_dynamic_instructions,
)
from suzent.skills import get_skill_manager

# Import memory lifecycle functions (for backward compatibility re-exports)
from suzent.memory.lifecycle import (
    get_memory_manager,
)

# Suppress LiteLLM's verbose logging
os.environ["LITELLM_LOG"] = "ERROR"

logger = get_logger(__name__)


# --- Agent State ---
agent_instance: Optional[Agent] = None
agent_config: Optional[dict] = None
agent_lock = asyncio.Lock()


def _build_mcp_servers(config: Dict[str, Any]) -> List:
    """
    Build MCP server toolset instances from the enabled servers in config.

    Returns a list of MCPServerStreamableHTTP / MCPServerStdio instances
    that can be passed as ``toolsets`` to a pydantic-ai Agent.
    """
    mcp_enabled = config.get("mcp_enabled")
    if mcp_enabled is None:
        mcp_enabled = CONFIG.mcp_enabled or {}

    raw_mcp_urls = config.get("mcp_urls", CONFIG.mcp_urls)
    mcp_headers = config.get("mcp_headers", {})
    mcp_stdio_params = config.get("mcp_stdio_params", CONFIG.mcp_stdio_params)

    # Parse mcp_urls to handle both simple and nested formats
    mcp_urls = {}

    if isinstance(raw_mcp_urls, list):
        for i, url in enumerate(raw_mcp_urls):
            mcp_urls[f"mcp-url-{i}"] = url
    elif isinstance(raw_mcp_urls, dict):
        for name, value in raw_mcp_urls.items():
            if isinstance(value, str):
                mcp_urls[name] = value
            elif isinstance(value, dict):
                mcp_urls[name] = value.get("url", "")
                if value.get("headers") and name not in mcp_headers:
                    mcp_headers[name] = value["headers"]

    servers = []

    # Build URL servers
    for name, url in mcp_urls.items():
        if mcp_enabled.get(name, False) and url:
            headers = mcp_headers.get(name)
            server = MCPServerStreamableHTTP(
                url,
                headers=headers,
                tool_prefix=name,
            )
            servers.append(server)

    # Build stdio servers
    if mcp_stdio_params:
        for name, params in mcp_stdio_params.items():
            if mcp_enabled.get(name, False):
                server = MCPServerStdio(
                    params["command"],
                    args=params.get("args", []),
                    env=params.get("env"),
                    tool_prefix=name,
                )
                servers.append(server)

    return servers


def create_agent(
    config: Dict[str, Any], memory_context: Optional[str] = None
) -> Agent[AgentDeps, str]:
    """
    Creates a pydantic-ai Agent based on the provided configuration.

    Args:
        config: Configuration dictionary containing:
            - model: Model identifier (e.g., "gemini/gemini-2.5-pro")
            - tools: List of tool names to enable
            - memory_enabled: Whether to equip memory tools (default: False)
            - mcp_urls: Optional MCP server URLs
            - instructions: Optional custom instructions

    Returns:
        Configured pydantic-ai Agent instance.
    """
    # --- Validate model ---
    enabled_models = get_enabled_models_from_db()

    if not enabled_models:
        if CONFIG.model_options:
            enabled_models = CONFIG.model_options
        else:
            raise ValueError(
                "No LLM models are enabled. Please configure a provider in Settings."
            )

    model_id = config.get("model")

    if not model_id or model_id not in enabled_models:
        fallback = enabled_models[0]
        if model_id:
            logger.warning(
                f"Requested model '{model_id}' is not enabled. Falling back to '{fallback}'."
            )
        model_id = fallback

    model = create_pydantic_ai_model(model_id)

    # --- Build tool list ---
    tool_names = (config.get("tools") or CONFIG.default_tools).copy()
    memory_enabled = config.get("memory_enabled", CONFIG.memory_enabled)

    from suzent.tools.registry import get_tool_function, get_tool_session_guidance

    tool_functions = []
    enabled_tool_names = set(tool_names)
    _auto_equipped = {
        "MemorySearchTool",
        "MemoryBlockUpdateTool",
        "SkillTool",
        "SocialMessageTool",
    }

    for tool_name in tool_names:
        if tool_name in _auto_equipped:
            continue
        fn = get_tool_function(tool_name)
        if fn:
            tool_functions.append(fn)
        else:
            logger.warning(f"Tool function not found for: {tool_name}")

    # Equip memory tools if enabled
    if memory_enabled and CONFIG.memory_enabled:
        mem_search = get_tool_function("MemorySearchTool")
        mem_update = get_tool_function("MemoryBlockUpdateTool")
        if mem_search:
            tool_functions.append(mem_search)
            enabled_tool_names.add("MemorySearchTool")
        if mem_update:
            tool_functions.append(mem_update)
            enabled_tool_names.add("MemoryBlockUpdateTool")

    # Auto-equip SkillTool if any skills are enabled
    skill_manager = get_skill_manager()
    if skill_manager.enabled_skills:
        fn = get_tool_function("SkillTool")
        if fn and fn not in tool_functions:
            tool_functions.append(fn)
            enabled_tool_names.add("SkillTool")
            logger.info(
                f"SkillTool equipped ({len(skill_manager.enabled_skills)} skills enabled)"
            )

    # Auto-equip SocialMessageTool
    social_ctx = config.get("social_context")
    if social_ctx or "SocialMessageTool" in tool_names:
        fn = get_tool_function("SocialMessageTool")
        if fn and fn not in tool_functions:
            tool_functions.append(fn)
            enabled_tool_names.add("SocialMessageTool")

    # --- Build MCP servers ---
    mcp_servers = _build_mcp_servers(config)

    # --- Build instructions ---
    base_instructions = config.get("instructions", CONFIG.instructions)
    session_guidance_items = get_tool_session_guidance(sorted(enabled_tool_names))

    # --- Create pydantic-ai Agent ---
    agent = Agent(
        model,
        deps_type=AgentDeps,
        tools=tool_functions,
        toolsets=mcp_servers if mcp_servers else [],
        instructions=STATIC_INSTRUCTIONS,
        output_type=[str, DeferredToolRequests],
        output_retries=3,
    )

    register_dynamic_instructions(
        agent,
        base_instructions=base_instructions,
        memory_context=memory_context,
        session_guidance_items=session_guidance_items,
    )

    # Store metadata for later introspection
    agent._tool_names = [tn for tn in tool_names]  # type: ignore[attr-defined]
    agent._model_id = model_id  # type: ignore[attr-defined]

    return agent


def build_agent_config(
    base_config: Optional[Dict[str, Any]] = None, require_social_tool: bool = False
) -> Dict[str, Any]:
    """
    Builds the effective configuration dictionary for a ChatProcessor turn,
    merging base configs with user preferences from the database.

    Args:
        base_config: Initial configuration overrides (e.g., from request).
        require_social_tool: If True, ensures SocialMessageTool is equipped.

    Returns:
        A dictionary containing the merged configuration.
    """
    from suzent.database import get_database

    config = base_config.copy() if base_config else {}

    try:
        db = get_database()
        if prefs := db.get_user_preferences():
            if not config.get("model") and prefs.model:
                config["model"] = prefs.model
            if not config.get("agent") and prefs.agent:
                config["agent"] = prefs.agent
            if "tools" not in config and prefs.tools is not None:
                config["tools"] = prefs.tools
    except Exception as e:
        logger.warning(f"Failed to load user preferences: {e}")

    # Ensure tools list exists and is populated
    tools = config.get("tools")
    if tools is None:
        tools = CONFIG.default_tools.copy()
    elif isinstance(tools, list):
        tools = tools.copy()

    if require_social_tool and "SocialMessageTool" not in tools:
        tools.append("SocialMessageTool")

    config["tools"] = tools

    return config


async def get_or_create_agent(config: Dict[str, Any], reset: bool = False) -> Agent:
    """
    Get the current agent instance or create a new one if needed.

    Args:
        config: Agent configuration dictionary.
        reset: If True, force creation of a new agent instance.

    Returns:
        pydantic-ai Agent instance ready for use.
    """
    global agent_instance, agent_config

    _TRANSIENT_KEYS = {"_runtime", "_chat_id", "_user_id"}

    def _stable_config(cfg: dict) -> dict:
        return {k: v for k, v in cfg.items() if k not in _TRANSIENT_KEYS}

    async with agent_lock:
        config_changed = _stable_config(config) != (
            _stable_config(agent_config) if agent_config else None
        )
        if config_changed and agent_config is not None:
            logger.info("Config changed - creating new agent")

        if agent_instance is None or config_changed or reset:
            # Fetch memory context if memory system is enabled
            memory_context = None
            memory_enabled = config.get("memory_enabled", False)
            mem_manager = get_memory_manager()
            if mem_manager and memory_enabled:
                chat_id = config.get("_chat_id")
                user_id = config.get("_user_id", "default-user")
                sandbox_enabled = config.get("sandbox_enabled", CONFIG.sandbox_enabled)
                try:
                    memory_context = await mem_manager.format_core_memory_for_context(
                        chat_id=chat_id,
                        user_id=user_id,
                        sandbox_enabled=sandbox_enabled,
                    )
                    if memory_context:
                        logger.debug(f"Fetched core memory context for user={user_id}")
                except Exception as e:
                    logger.error(f"Error fetching memory context: {e}")
                    memory_context = None

            agent_instance = create_agent(config, memory_context=memory_context)
            agent_config = config

        return agent_instance
