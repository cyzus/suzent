"""
Agent management module for creating, serializing, and managing agent state.

This module handles the lifecycle of AI agents including:
- Creating agents with specified configurations
- Serializing agent state for persistence
- Deserializing and restoring agent state
- Managing global agent instances
- Memory system integration
"""

import asyncio
import importlib
import pickle
import os
from typing import Optional, Dict, Any, List
from mcp import StdioServerParameters

from smolagents import CodeAgent, ToolCallingAgent, LiteLLMModel, MCPClient
from smolagents.tools import Tool

from suzent.config import CONFIG, PROJECT_DIR
from suzent.logger import get_logger
from suzent.prompts import format_instructions
# Late imports for tools to avoid circular deps during init if needed,
# but imported at scope where used is generally cleaner if conditional.
# However, for this refactor, we'll import PathResolver inside the helper.


# Suppress LiteLLM's verbose logging
os.environ["LITELLM_LOG"] = "ERROR"

logger = get_logger(__name__)


# --- Agent State ---
agent_instance: Optional[CodeAgent] = None
agent_config: Optional[dict] = None
agent_lock = asyncio.Lock()

# --- Memory System State ---
memory_manager = None
memory_store = None
main_event_loop = None  # Store reference to main event loop for async operations


async def init_memory_system() -> bool:
    """
    Initialize the memory system if enabled in configuration.

    Returns:
        True if memory system initialized successfully, False otherwise.
    """
    global memory_manager, memory_store, main_event_loop

    # Store reference to main event loop
    import asyncio

    main_event_loop = asyncio.get_running_loop()

    if not CONFIG.memory_enabled:
        logger.info("Memory system disabled in configuration")
        return False

    try:
        # Import memory modules
        from suzent.memory import MemoryManager, PostgresMemoryStore

        # Get PostgreSQL connection string from environment
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = os.getenv("POSTGRES_PORT", "5430")
        db = os.getenv("POSTGRES_DB", "suzent")
        user = os.getenv("POSTGRES_USER", "suzent")
        password = os.getenv("POSTGRES_PASSWORD", "ultra_secret")
        postgres_conn = f"postgresql://{user}:{password}@{host}:{port}/{db}"

        # Initialize PostgreSQL store
        memory_store = PostgresMemoryStore(postgres_conn)
        await memory_store.connect()

        # Initialize memory manager
        memory_manager = MemoryManager(
            store=memory_store,
            embedding_model=CONFIG.embedding_model,
            embedding_dimension=CONFIG.embedding_dimension,
            llm_for_extraction=CONFIG.extraction_model,
        )

        logger.info(
            f"Memory system initialized successfully (extraction: {'LLM' if CONFIG.extraction_model else 'heuristic'})"
        )

        # Add memory tools to CONFIG.tool_options so they appear in frontend
        if "MemorySearchTool" not in CONFIG.tool_options:
            CONFIG.tool_options.extend(["MemorySearchTool", "MemoryBlockUpdateTool"])
            logger.info("Added memory tools to config")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize memory system: {e}")
        memory_manager = None
        memory_store = None
        return False


async def shutdown_memory_system():
    """Shutdown memory system and close connections."""
    global memory_store

    if memory_store:
        try:
            await memory_store.close()
            logger.info("Memory system shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down memory system: {e}")


def get_memory_manager():
    """
    Get the global memory manager instance.

    Returns:
        MemoryManager instance or None if not initialized.
    """
    return memory_manager


def _create_memory_tools() -> list:
    """
    Create memory tool instances.

    Returns:
        List of memory tool instances, or empty list if memory not initialized.
    """
    if memory_manager is None:
        logger.warning("Memory system not initialized, skipping memory tools")
        return []

    try:
        from suzent.memory import MemorySearchTool, MemoryBlockUpdateTool

        tools = []

        # Create MemorySearchTool
        search_tool = MemorySearchTool(memory_manager)
        search_tool._main_loop = main_event_loop
        tools.append(search_tool)

        # Create MemoryBlockUpdateTool
        update_tool = MemoryBlockUpdateTool(memory_manager)
        update_tool._main_loop = main_event_loop
        tools.append(update_tool)

        logger.info("Memory tools equipped")
        return tools

    except Exception as e:
        logger.error(f"Failed to create memory tools: {e}")
        return []


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
    # Extract configuration with CONFIG-based fallbacks
    model_id = config.get("model") or (
        CONFIG.model_options[0] if CONFIG.model_options else "gemini/gemini-2.5-pro"
    )
    agent_name = config.get("agent") or (
        CONFIG.agent_options[0] if CONFIG.agent_options else "CodeAgent"
    )
    tool_names = (config.get("tools") or CONFIG.default_tools).copy()
    memory_enabled = config.get("memory_enabled", CONFIG.memory_enabled)
    sandbox_enabled = config.get("sandbox_enabled", CONFIG.sandbox_enabled)
    additional_authorized_imports = (
        config.get("additional_authorized_imports")
        or CONFIG.additional_authorized_imports
    )
    model = LiteLLMModel(model_id=model_id)

    tools = []

    # Mapping of tool class names to their module file names
    tool_module_map = {
        "WebSearchTool": "websearch_tool",
        "PlanningTool": "planning_tool",
        "WebpageTool": "webpage_tool",
        "ReadFileTool": "read_file_tool",
        "WriteFileTool": "write_file_tool",
        "EditFileTool": "edit_file_tool",
        "GlobTool": "glob_tool",
        "GrepTool": "grep_tool",
        "BashTool": "bash_tool",
        "SkillTool": "skill_tool",
    }

    # Load regular tools (excluding memory tools)
    custom_tool_names = tool_names

    for tool_name in custom_tool_names:
        try:
            # Skip memory and sandbox tools - they are handled separately
            if tool_name in [
                "MemorySearchTool",
                "MemoryBlockUpdateTool",
                "SandboxTool",
                "BashTool",
            ]:
                continue

            module_file_name = tool_module_map.get(tool_name)
            if not module_file_name:
                logger.warning(f"No module mapping found for tool {tool_name}")
                continue

            tool_module = importlib.import_module(f"suzent.tools.{module_file_name}")
            # Get the tool class from the module
            tool_class = getattr(tool_module, tool_name)
            # Instantiate the tool if it's a subclass of Tool
            if issubclass(tool_class, Tool):
                tools.append(tool_class())
            else:
                logger.warning(f"{tool_name} is not a valid Tool class")
        except (ImportError, AttributeError) as e:
            logger.error(f"Could not load tool {tool_name}: {e}")

    # Equip memory tools separately if enabled
    if memory_enabled and CONFIG.memory_enabled:
        memory_tools = _create_memory_tools()
        tools.extend(memory_tools)

    # Equip sandbox tool if enabled
    if sandbox_enabled:
        try:
            # We can use the mapping if available, or just import directly
            tool_module = importlib.import_module("suzent.tools.bash_tool")
            tool_class = getattr(tool_module, "BashTool")
            # Check if not already added to avoid duplicates
            if not any(isinstance(t, tool_class) for t in tools):
                tools.append(tool_class())
                logger.info("BashTool equipped (Sandbox enabled)")
        except Exception as e:
            logger.error(f"Failed to equip BashTool: {e}")

    # --- Filter MCP servers by enabled state if provided ---
    # Accepts: config['mcp_enabled'] = {name: bool, ...}, config['mcp_urls'], config['mcp_stdio_params']
    mcp_enabled = config.get("mcp_enabled")
    mcp_urls = config.get("mcp_urls", CONFIG.mcp_urls)
    mcp_stdio_params = config.get("mcp_stdio_params", CONFIG.mcp_stdio_params)

    mcp_server_parameters = []
    if mcp_enabled is not None:
        # Only include explicitly enabled servers
        # Default to False (disabled) if server not in mcp_enabled dict
        if mcp_urls:
            for name, url in (
                mcp_urls.items() if isinstance(mcp_urls, dict) else enumerate(mcp_urls)
            ):
                if mcp_enabled.get(name, False):
                    mcp_server_parameters.append(
                        {"url": url, "transport": "streamable-http"}
                    )
        if mcp_stdio_params:
            for name, params in mcp_stdio_params.items():
                if mcp_enabled.get(name, False):
                    mcp_server_parameters.append(StdioServerParameters(**params))
    # Note: If mcp_enabled is not provided, default to NO MCP servers
    # This ensures fresh launch matches frontend tool display (only native tools)

    if mcp_server_parameters:
        mcp_client = MCPClient(server_parameters=mcp_server_parameters)
        tools.extend(mcp_client.get_tools())

    agent_map = {"CodeAgent": CodeAgent, "ToolcallingAgent": ToolCallingAgent}

    agent_class = agent_map.get(agent_name)
    if not agent_class:
        raise ValueError(f"Unknown agent: {agent_name}")

    base_instructions = config.get("instructions", CONFIG.instructions)
    instructions = format_instructions(base_instructions)

    # Inject memory context if provided (fetched in async context by get_or_create_agent)
    if memory_context:
        instructions = f"{instructions}\n\n{memory_context}"

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


def _sanitize_memory(memory):
    """
    Sanitize agent memory to remove non-serializable objects like AgentError.
    AgentError contains a logger which can't be pickled, and its signature may change
    between library versions causing unpickling to fail.

    Args:
        memory: Agent memory (list of message dicts or other structure).

    Returns:
        Sanitized memory safe for pickling.
    """
    from smolagents.memory import ActionStep

    # First pass: clear all error fields from ActionStep objects IN-PLACE
    # This must be done before any copy attempts
    errors_cleared = 0

    def clear_errors(value):
        """Clear error fields from ActionStep objects."""
        nonlocal errors_cleared
        if isinstance(value, ActionStep):
            if hasattr(value, "error") and value.error is not None:
                logger.debug(
                    f"Clearing error from ActionStep: {type(value.error).__name__}"
                )
                value.error = None
                errors_cleared += 1
        elif isinstance(value, list):
            for item in value:
                clear_errors(item)
        elif isinstance(value, dict):
            for v in value.values():
                clear_errors(v)
        elif hasattr(value, "steps"):  # Memory object with steps attribute
            logger.debug(f"Sanitizing Memory object with {len(value.steps)} steps")
            clear_errors(value.steps)

    try:
        # Clear errors in-place first (safe because errors are not needed for restoration)
        clear_errors(memory)

        if errors_cleared > 0:
            logger.debug(
                f"Cleared {errors_cleared} AgentError objects from memory before serialization"
            )

        # Now return the cleaned memory
        return memory

    except Exception as e:
        logger.error(f"Error sanitizing memory: {e}")
        # Return empty memory rather than risk corrupt state
        return []


def serialize_agent(agent: CodeAgent) -> Optional[bytes]:
    """
    Serialize an agent and its complete state to bytes.
    This preserves all memory, configuration, and internal state.

    Args:
        agent: The agent instance to serialize.

    Returns:
        Serialized agent state as bytes, or None if serialization fails.
    """
    try:
        # Extract only the serializable parts we need
        tool_attr = getattr(agent, "_tool_instances", None)
        if tool_attr is None:
            raw_tools = getattr(agent, "tools", None)
            if isinstance(raw_tools, dict):
                tool_iterable = raw_tools.values()
            elif isinstance(raw_tools, (list, tuple)):
                tool_iterable = raw_tools
            elif raw_tools is None:
                tool_iterable = []
            else:
                tool_iterable = [raw_tools]
        else:
            tool_iterable = tool_attr

        tool_names = []
        for tool in tool_iterable:
            try:
                name = tool.__class__.__name__
            except AttributeError:
                continue
            if name not in tool_names:
                tool_names.append(name)

        # Sanitize memory to remove AgentError objects that can't be pickled
        logger.debug(
            f"Sanitizing memory before serialization (type: {type(agent.memory)})"
        )
        sanitized_memory = _sanitize_memory(agent.memory)
        logger.debug("Memory sanitization complete")

        serializable_state = {
            "memory": sanitized_memory,
            "model_id": getattr(agent.model, "model_id", None)
            if hasattr(agent, "model")
            else None,
            "instructions": getattr(agent, "instructions", None),
            "step_number": getattr(agent, "step_number", 1),
            "max_steps": getattr(agent, "max_steps", 10),
            # Store tool names/types instead of tool instances
            "tool_names": tool_names,
            # Store managed agent info if any
            "managed_agents": getattr(agent, "managed_agents", []),
        }

        # Serialize to bytes
        return pickle.dumps(serializable_state)
    except Exception as e:
        logger.error(f"Error serializing agent: {e}")
        return None


def deserialize_agent(agent_data: bytes, config: Dict[str, Any]) -> Optional[CodeAgent]:
    """
    Deserialize agent state and restore it to a new agent instance.

    Args:
        agent_data: Serialized agent state as bytes.
        config: Configuration dictionary for creating the agent.

    Returns:
        Restored agent instance, or None if deserialization fails.
    """
    if not agent_data:
        return None

    try:
        # Try to deserialize the state
        try:
            # Use standard pickle first (custom unpickler doesn't actually help with this issue)
            state = pickle.loads(agent_data)
        except (TypeError, AttributeError, pickle.UnpicklingError) as unpickle_error:
            # Log the ACTUAL error to help debug what's wrong
            import traceback

            logger.error(f"Failed to unpickle agent state: {unpickle_error}")
            logger.debug(f"Unpickling traceback:\n{traceback.format_exc()}")

            error_msg = str(unpickle_error)
            if "AgentError" in error_msg or "logger" in error_msg:
                logger.info(
                    "Agent state contains incompatible AgentError, will be cleared"
                )
            else:
                logger.warning(f"Unpickling failed for unknown reason: {error_msg}")
            return None

        # Log what we got to help debug
        logger.debug(f"Unpickled state type: {type(state)}")
        if isinstance(state, dict):
            logger.debug(f"State dict keys: {list(state.keys())}")
        else:
            # State is not a dict - might be from new format (just memory object)
            logger.warning(
                f"Agent state is not a dict (type: {type(state).__name__}), expected old format with dict. Creating fresh agent."
            )
            return None

        # Create a new agent with the config that was passed in
        # This allows config changes (tool changes, model changes) to take effect
        # We only restore memory, not the configuration
        agent = create_agent(config)

        # Restore the memory and state
        if "memory" in state:
            agent.memory = state["memory"]

        # Restore other important state
        if "step_number" in state:
            agent.step_number = state["step_number"]
        if "max_steps" in state:
            agent.max_steps = state["max_steps"]
        # We deliberately do NOT restore 'instructions' from state, as they might contain
        # outdated tool definitions or stale system prompts. We rely on create_agent(config)
        # to generate the correct fresh prompt based on current config/tools.
        # if 'instructions' in state and state['instructions']:
        #     agent.instructions = state['instructions']

        return agent

    except Exception as e:
        logger.warning(
            f"Error deserializing agent state: {e}. Starting with fresh agent."
        )
        return None


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

    async with agent_lock:
        # Re-create agent if config changes, reset requested, or not initialized
        config_changed = config != agent_config
        if config_changed and agent_config is not None:
            logger.info("Config changed - creating new agent")
            logger.debug(f"Old config tools: {agent_config.get('tools', [])}")
            logger.debug(f"New config tools: {config.get('tools', [])}")

        if agent_instance is None or config_changed or reset:
            # Fetch memory context if memory system is enabled (in async context)
            memory_context = None
            memory_enabled = config.get("memory_enabled", False)
            if memory_manager and memory_enabled:
                chat_id = config.get("_chat_id")
                user_id = config.get("_user_id", "default-user")
                try:
                    memory_context = (
                        await memory_manager.format_core_memory_for_context(
                            chat_id=chat_id, user_id=user_id
                        )
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

    from suzent.config import CONFIG

    # Use configured user_id if not provided
    if user_id is None:
        user_id = CONFIG.user_id

    # --- Dynamic Sandbox Tool Management ---
    # Determine effective sandbox status
    sandbox_enabled = (
        config.get("sandbox_enabled", CONFIG.sandbox_enabled)
        if config
        else CONFIG.sandbox_enabled
    )

    if not sandbox_enabled:
        # Remove BashTool if present
        # Update agent.tools dictionary if it exists
        if hasattr(agent, "tools") and isinstance(agent.tools, dict):
            if "BashTool" in agent.tools:
                del agent.tools["BashTool"]

        # Update _tool_instances list
        agent._tool_instances = [
            t for t in agent._tool_instances if t.__class__.__name__ != "BashTool"
        ]

        # Also check agent.toolbox if it exists (smolagents structure)
        if (
            hasattr(agent, "toolbox")
            and hasattr(agent.toolbox, "tools")
            and isinstance(agent.toolbox.tools, dict)
        ):
            if "BashTool" in agent.toolbox.tools:
                del agent.toolbox.tools["BashTool"]

    else:
        # Add BashTool if missing
        has_bash = any(
            t.__class__.__name__ == "BashTool" for t in agent._tool_instances
        )
        if not has_bash:
            try:
                from suzent.tools.bash_tool import BashTool

                bash_tool = BashTool()
                agent._tool_instances.append(bash_tool)
                if hasattr(agent, "tools") and isinstance(agent.tools, dict):
                    agent.tools["BashTool"] = bash_tool
            except Exception as e:
                logger.error(f"Failed to dynamically equip BashTool: {e}")

    # --- Tool Context Injection ---
    for tool_instance in agent._tool_instances:
        # Inject chat_id for tools like PlanningTool
        if hasattr(tool_instance, "set_chat_context"):
            tool_instance.set_chat_context(chat_id)

        # Inject user_id and chat_id for memory tools
        if tool_instance.__class__.__name__ in [
            "MemorySearchTool",
            "MemoryBlockUpdateTool",
        ]:
            if hasattr(tool_instance, "set_context"):
                tool_instance.set_context(chat_id=chat_id, user_id=user_id)

        # Inject chat_id and custom volumes for BashTool
        if tool_instance.__class__.__name__ == "BashTool":
            tool_instance.chat_id = chat_id
            # Inject per-chat sandbox volumes if configured
            volumes = _get_effective_volumes(config)

            if volumes and hasattr(tool_instance, "set_custom_volumes"):
                tool_instance.set_custom_volumes(volumes)

        # Inject PathResolver into file tools
        file_tool_names = [
            "ReadFileTool",
            "WriteFileTool",
            "EditFileTool",
            "GlobTool",
            "GrepTool",
        ]
        if tool_instance.__class__.__name__ in file_tool_names:
            if hasattr(tool_instance, "set_context"):
                resolver = _create_path_resolver(chat_id, config)
                tool_instance.set_context(resolver)


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

    # 1. Determine sandbox_enabled (Chat Config > Global Config)
    sandbox_enabled = (
        config.get("sandbox_enabled", CONFIG.sandbox_enabled)
        if config
        else CONFIG.sandbox_enabled
    )

    # 2. Determine sandbox_volumes (Chat Config > Global Config) and auto-mounts
    custom_volumes = _get_effective_volumes(config)

    # logger.debug(f"Creating PathResolver for {chat_id} with volumes: {custom_volumes}")
    return PathResolver(chat_id, sandbox_enabled, custom_volumes=custom_volumes)

def _get_effective_volumes(config: Optional[dict]) -> List[str]:
    """
    Calculate effective sandbox volumes, including auto-mounted skills directory.
    """
    custom_volumes = config.get("sandbox_volumes") if config else None
    if not custom_volumes:
        custom_volumes = CONFIG.sandbox_volumes
        
    volumes = list(custom_volumes) if custom_volumes else []
    
    # Auto-mount skills directory
    # Host path: relative 'skills' -> resolves to {container_workspace}/skills in SandboxManager
    # Container path: /mnt/skills
    mount_str = "skills:/mnt/skills"
    
    # Check if already present (naive check)
    if mount_str not in volumes:
        volumes.append(mount_str)
    

    return volumes


