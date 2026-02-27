"""
Agent management module for creating, serializing, and managing agent state.

This module handles the lifecycle of AI agents including:
- Creating agents with specified configurations
- Serializing agent state for persistence
- Deserializing and restoring agent state
- Managing global agent instances
"""

import asyncio
import os
from typing import Optional, Dict, Any
from mcp import StdioServerParameters

from smolagents import CodeAgent, ToolCallingAgent, LiteLLMModel, MCPClient
from suzent.core.provider_factory import get_enabled_models_from_db

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.prompts import format_instructions, build_social_context
from suzent.skills import get_skill_manager
from suzent.config import get_effective_volumes

# Import memory lifecycle functions (for backward compatibility re-exports)
from suzent.memory.lifecycle import (
    get_memory_manager,
    create_memory_tools,
)

# Import serialization functions
from suzent.core.agent_serializer import (
    deserialize_agent as _deserialize_agent_impl,
)

# Suppress LiteLLM's verbose logging
os.environ["LITELLM_LOG"] = "ERROR"

logger = get_logger(__name__)


# --- Agent State ---
agent_instance: Optional[CodeAgent] = None
agent_config: Optional[dict] = None
agent_lock = asyncio.Lock()


def _build_mcp_tools(config: Dict[str, Any]) -> list:
    """
    Build MCP tools from the enabled servers in the configuration.

    Supports both simple format: {"name": "url"}
    and nested format: {"name": {"url": "...", "headers": {...}}}

    Args:
        config: Agent configuration dictionary containing:
            - mcp_enabled: Dict mapping server names to enabled state
            - mcp_urls: URL servers (simple or nested format)
            - mcp_headers: Optional headers per server
            - mcp_stdio_params: Stdio server parameters

    Returns:
        List of MCP tools from enabled servers.
    """
    mcp_enabled = config.get("mcp_enabled")

    # If mcp_enabled is not provided, fallback to global CONFIG defaults
    if mcp_enabled is None:
        mcp_enabled = CONFIG.mcp_enabled or {}

    raw_mcp_urls = config.get("mcp_urls", CONFIG.mcp_urls)
    mcp_headers = config.get("mcp_headers", {})
    mcp_stdio_params = config.get("mcp_stdio_params", CONFIG.mcp_stdio_params)

    # Parse mcp_urls to handle both simple and nested formats
    mcp_urls = {}

    # Handle list input (backward compatibility for array of strings)
    if isinstance(raw_mcp_urls, list):
        for i, url in enumerate(raw_mcp_urls):
            # Use generated name if we can't infer it. Headers won't work for these.
            # Ideally we could reverse-lookup global config but that's complex/unreliable if duplicates exist.
            mcp_urls[f"mcp-url-{i}"] = url

    # Handle dict input (standard format)
    elif isinstance(raw_mcp_urls, dict):
        for name, value in raw_mcp_urls.items():
            if isinstance(value, str):
                mcp_urls[name] = value
            elif isinstance(value, dict):
                mcp_urls[name] = value.get("url", "")
                # Extract headers from nested format if not already provided
                if value.get("headers") and name not in mcp_headers:
                    mcp_headers[name] = value["headers"]

    mcp_server_parameters = []

    # Build URL server parameters
    for name, url in mcp_urls.items():
        if mcp_enabled.get(name, False):
            server_params = {"url": url, "transport": "streamable-http"}
            if name in mcp_headers and mcp_headers[name]:
                server_params["headers"] = mcp_headers[name]
            mcp_server_parameters.append(server_params)

    # Build stdio server parameters
    if mcp_stdio_params:
        for name, params in mcp_stdio_params.items():
            if mcp_enabled.get(name, False):
                mcp_server_parameters.append(StdioServerParameters(**params))

    if not mcp_server_parameters:
        return []

    mcp_client = MCPClient(server_parameters=mcp_server_parameters)
    return mcp_client.get_tools()


def create_agent(
    config: Dict[str, Any], memory_context: Optional[str] = None
) -> CodeAgent:
    """
    Creates an agent based on the provided configuration.

    Args:
        config: Configuration dictionary containing:
            - model: Model identifier (e.g., "gemini/gemini-2.5-pro")
            - agent: Agent type (e.g., "CodeAgent")
            - tools: List of tool names to enable
            - memory_enabled: Whether to equip memory tools (default: False)
            - mcp_urls: Optional list of MCP server URLs
            - instructions: Optional custom instructions

    Returns:
        Configured CodeAgent instance with specified tools and model.

    Raises:
        ValueError: If an unknown agent type is specified.
    """
    # Extract configuration with CONFIG-based fallbacks and validate model

    enabled_models = get_enabled_models_from_db()

    if not enabled_models:
        # Fallback to CONFIG defaults if DB check returns nothing (should fallback in helper, but double check)
        if CONFIG.model_options:
            enabled_models = CONFIG.model_options
        else:
            # Critical failure if no models available anywhere
            raise ValueError(
                "No LLM models are enabled. Please configure a provider in Settings."
            )

    model_id = config.get("model")

    # Check if requested model is valid/enabled
    if not model_id or model_id not in enabled_models:
        fallback = enabled_models[0]
        if model_id:
            logger.warning(
                f"Requested model '{model_id}' is not enabled. Falling back to '{fallback}'."
            )
        model_id = fallback
    agent_name = config.get("agent") or (
        CONFIG.agent_options[0] if CONFIG.agent_options else "CodeAgent"
    )
    tool_names = (config.get("tools") or CONFIG.default_tools).copy()
    memory_enabled = config.get("memory_enabled", CONFIG.memory_enabled)
    additional_authorized_imports = (
        config.get("additional_authorized_imports")
        or CONFIG.additional_authorized_imports
    )
    model = LiteLLMModel(model_id=model_id)

    tools = []

    # Import tool registry for dynamic tool discovery
    from suzent.tools.registry import get_tool_class

    # Tools auto-equipped separately below
    _auto_equipped = {
        "MemorySearchTool",
        "MemoryBlockUpdateTool",
        "SkillTool",
        "SocialMessageTool",
    }

    for tool_name in tool_names:
        try:
            if tool_name in _auto_equipped:
                continue

            tool_class = get_tool_class(tool_name)
            if tool_class is None:
                logger.warning(f"Tool not found in registry: {tool_name}")
                continue

            tools.append(tool_class())
        except Exception as e:
            logger.error(f"Could not load tool {tool_name}: {e}")

    # Equip memory tools separately if enabled
    if memory_enabled and CONFIG.memory_enabled:
        memory_tools = create_memory_tools()
        tools.extend(memory_tools)

    # Auto-equip SkillTool if any skills are enabled
    skill_manager = get_skill_manager()
    if skill_manager.enabled_skills:
        try:
            skill_tool_class = get_tool_class("SkillTool")
            if skill_tool_class:
                # Check if not already added
                if not any(isinstance(t, skill_tool_class) for t in tools):
                    tools.append(skill_tool_class())
                    logger.info(
                        f"SkillTool equipped ({len(skill_manager.enabled_skills)} skills enabled)"
                    )
        except Exception as e:
            logger.error(f"Failed to equip SkillTool: {e}")

    # Auto-equip SocialMessageTool (social mode via context, or desktop mode via tool list)
    social_ctx = config.get("social_context")
    if social_ctx or "SocialMessageTool" in tool_names:
        try:
            social_tool_class = get_tool_class("SocialMessageTool")
            if social_tool_class and not any(
                isinstance(t, social_tool_class) for t in tools
            ):
                tools.append(social_tool_class())
        except Exception as e:
            logger.error(f"Failed to equip SocialMessageTool: {e}")

    # Load MCP tools from enabled servers
    mcp_tools = _build_mcp_tools(config)
    tools.extend(mcp_tools)

    agent_map = {"CodeAgent": CodeAgent, "ToolcallingAgent": ToolCallingAgent}

    agent_class = agent_map.get(agent_name)
    if not agent_class:
        raise ValueError(f"Unknown agent: {agent_name}")

    base_instructions = config.get("instructions", CONFIG.instructions)

    # Calculate effective custom volumes to report in prompt
    sandbox_volumes = config.get("sandbox_volumes")
    custom_volumes = get_effective_volumes(sandbox_volumes)

    instructions = format_instructions(
        base_instructions,
        memory_context=memory_context,
        custom_volumes=custom_volumes,
        social_context=build_social_context(social_ctx) if social_ctx else "",
    )

    params = {
        "model": model,
        "tools": tools,
        "stream_outputs": True,
        "instructions": instructions,
    }

    if agent_name == "CodeAgent" and additional_authorized_imports:
        params["additional_authorized_imports"] = additional_authorized_imports

    agent = agent_class(**params)
    # Store tool instances on the agent for later context injection
    agent._tool_instances = tools
    return agent


def deserialize_agent(agent_data: bytes, config: Dict[str, Any]) -> Optional[CodeAgent]:
    """
    Deserialize agent state and restore it to a new agent instance.

    Args:
        agent_data: Serialized agent state as bytes.
        config: Configuration dictionary for creating the agent.

    Returns:
        Restored agent instance, or None if deserialization fails.
    """
    return _deserialize_agent_impl(agent_data, config, create_agent)


def build_agent_config(
    base_config: Optional[Dict[str, Any]] = None, require_social_tool: bool = False
) -> Dict[str, Any]:
    """
    Builds the effective configuration dictionary for a ChatProcessor turn,
    merging base configs with user preferences from the database.

    Args:
        base_config: Initial configuration overrides (e.g., from request).
        require_social_tool: If True, ensures SocialMessageTool is equipped
                             (used by cron and heartbeat).

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


async def get_or_create_agent(config: Dict[str, Any], reset: bool = False) -> CodeAgent:
    """
    Get the current agent instance or create a new one if needed.

    Args:
        config: Agent configuration dictionary.
        reset: If True, force creation of a new agent instance.

    Returns:
        Agent instance ready for use.
    """
    global agent_instance, agent_config

    # Keys that are transient per-request and should not trigger agent re-creation
    # (_runtime contains live objects that can't be compared; _chat_id/_user_id are per-session)
    _TRANSIENT_KEYS = {"_runtime", "_chat_id", "_user_id"}

    def _stable_config(cfg: dict) -> dict:
        """Return config dict without transient per-request keys."""
        return {k: v for k, v in cfg.items() if k not in _TRANSIENT_KEYS}

    async with agent_lock:
        # Re-create agent if config changes, reset requested, or not initialized
        config_changed = _stable_config(config) != (
            _stable_config(agent_config) if agent_config else None
        )
        if config_changed and agent_config is not None:
            logger.info("Config changed - creating new agent")
            logger.debug(f"Old config tools: {agent_config.get('tools', [])}")
            logger.debug(f"New config tools: {config.get('tools', [])}")

        if agent_instance is None or config_changed or reset:
            # Fetch memory context if memory system is enabled (in async context)
            memory_context = None
            memory_enabled = config.get("memory_enabled", False)
            mem_manager = get_memory_manager()
            if mem_manager and memory_enabled:
                chat_id = config.get("_chat_id")
                user_id = config.get("_user_id", "default-user")
                try:
                    memory_context = await mem_manager.format_core_memory_for_context(
                        chat_id=chat_id, user_id=user_id
                    )
                    if memory_context:
                        logger.debug(f"Fetched core memory context for user={user_id}")
                except Exception as e:
                    logger.error(f"Error fetching memory context: {e}")
                    memory_context = None

            # Pass memory context to create_agent
            agent_instance = create_agent(config, memory_context=memory_context)
            agent_config = config

        return agent_instance
