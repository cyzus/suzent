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
from typing import Optional, Dict, Any
from mcp import StdioServerParameters

from smolagents import CodeAgent, ToolCallingAgent, LiteLLMModel, MCPClient
from smolagents.tools import Tool

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.prompts import format_instructions

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
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "suzent")
        user = os.getenv("POSTGRES_USER", "suzent")
        password = os.getenv("POSTGRES_PASSWORD", "password")
        postgres_conn = f"postgresql://{user}:{password}@{host}:{port}/{db}"

        # Initialize PostgreSQL store
        memory_store = PostgresMemoryStore(postgres_conn)
        await memory_store.connect()

        # Initialize memory manager
        memory_manager = MemoryManager(
            store=memory_store,
            embedding_model=CONFIG.embedding_model,
            embedding_dimension=CONFIG.embedding_dimension,
            llm_for_extraction=CONFIG.extraction_model
        )

        logger.info(f"Memory system initialized successfully (extraction: {'LLM' if CONFIG.extraction_model else 'heuristic'})")

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


def create_agent(config: Dict[str, Any], memory_context: Optional[str] = None) -> CodeAgent:
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
    model_id = config.get("model") or (CONFIG.model_options[0] if CONFIG.model_options else "gemini/gemini-2.5-pro")
    agent_name = config.get("agent") or (CONFIG.agent_options[0] if CONFIG.agent_options else "CodeAgent")
    tool_names = (config.get("tools") or CONFIG.default_tools).copy()
    memory_enabled = config.get("memory_enabled", CONFIG.memory_enabled)
    additional_authorized_imports = config.get("additional_authorized_imports") or CONFIG.additional_authorized_imports
    model = LiteLLMModel(model_id=model_id)

    tools = []

    # Mapping of tool class names to their module file names
    tool_module_map = {
        "WebSearchTool": "websearch_tool",
        "PlanningTool": "planning_tool",
        "WebpageTool": "webpage_tool",
        "FileTool": "file_tool",
        # Add other custom tools here as needed
    }

    # Load regular tools (excluding memory tools)
    custom_tool_names = tool_names

    for tool_name in custom_tool_names:
        try:
            # Skip memory tools - they are handled separately
            if tool_name in ["MemorySearchTool", "MemoryBlockUpdateTool"]:
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


    # --- Filter MCP servers by enabled state if provided ---
    # Accepts: config['mcp_enabled'] = {name: bool, ...}, config['mcp_urls'], config['mcp_stdio_params']
    mcp_enabled = config.get("mcp_enabled")
    mcp_urls = config.get("mcp_urls", CONFIG.mcp_urls)
    mcp_stdio_params = config.get("mcp_stdio_params", CONFIG.mcp_stdio_params)

    mcp_server_parameters = []
    if mcp_enabled is not None:
        # Only include enabled servers
        if mcp_urls:
            for name, url in (mcp_urls.items() if isinstance(mcp_urls, dict) else enumerate(mcp_urls)):
                if mcp_enabled.get(name, True):
                    mcp_server_parameters.append({"url": url, "transport": "streamable-http"})
        if mcp_stdio_params:
            for name, params in mcp_stdio_params.items():
                if mcp_enabled.get(name, True):
                    mcp_server_parameters.append(StdioServerParameters(**params))
    else:
        # Legacy: include all
        if mcp_urls:
            mcp_server_parameters.extend(
                [{"url": url, "transport": "streamable-http"} for url in (mcp_urls.values() if isinstance(mcp_urls, dict) else mcp_urls)]
            )
        if mcp_stdio_params:
            mcp_server_parameters.extend(
                [StdioServerParameters(**params) for server, params in mcp_stdio_params.items()]
            )

    if mcp_server_parameters:
        mcp_client = MCPClient(server_parameters=mcp_server_parameters)
        tools.extend(mcp_client.get_tools())



    agent_map = {
        "CodeAgent": CodeAgent,
        "ToolcallingAgent": ToolCallingAgent
    }

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

    agent = agent_class(
        **params
    )
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
    from smolagents.memory import ActionStep, FinalAnswerStep

    # First pass: clear all error fields from ActionStep objects IN-PLACE
    # This must be done before any copy attempts
    errors_cleared = 0
    
    def clear_errors(value):
        """Clear error fields from ActionStep objects."""
        nonlocal errors_cleared
        if isinstance(value, ActionStep):
            if hasattr(value, 'error') and value.error is not None:
                value.error = None
                errors_cleared += 1
        elif isinstance(value, list):
            for item in value:
                clear_errors(item)
        elif isinstance(value, dict):
            for v in value.values():
                clear_errors(v)
    
    try:
        # Clear errors in-place first (safe because errors are not needed for restoration)
        clear_errors(memory)
        
        if errors_cleared > 0:
            logger.debug(f"Cleared {errors_cleared} AgentError objects from memory before serialization")
        
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
        tool_attr = getattr(agent, '_tool_instances', None)
        if tool_attr is None:
            raw_tools = getattr(agent, 'tools', None)
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
        sanitized_memory = _sanitize_memory(agent.memory)

        serializable_state = {
            'memory': sanitized_memory,
            'model_id': getattr(agent.model, 'model_id', None) if hasattr(agent, 'model') else None,
            'instructions': getattr(agent, 'instructions', None),
            'step_number': getattr(agent, 'step_number', 1),
            'max_steps': getattr(agent, 'max_steps', 10),
            # Store tool names/types instead of tool instances
            'tool_names': tool_names,
            # Store managed agent info if any
            'managed_agents': getattr(agent, 'managed_agents', []),
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
            # If unpickling fails, it's likely due to incompatible AgentError objects
            # Log and return None so caller can clear the corrupted state
            error_msg = str(unpickle_error)
            if 'AgentError' in error_msg or 'logger' in error_msg or 'missing' in error_msg:
                logger.info(f"Agent state contains incompatible AgentError, will be cleared")
            else:
                logger.warning(f"Failed to unpickle agent state: {unpickle_error}")
            return None

        # Create a new agent with the same configuration
        # Use tool names from saved state to ensure consistency
        if 'tool_names' in state and state['tool_names']:
            # Map tool names back to config format
            tool_name_mapping = {
                'WebSearchTool': 'WebSearchTool',
                'PlanningTool': 'PlanningTool',
                'WebpageTool': 'WebpageTool',
                'FileTool': 'FileTool',
            }
            config_with_tools = config.copy()
            config_with_tools['tools'] = [
                tool_name_mapping.get(tool_name, tool_name)
                for tool_name in state['tool_names']
                if tool_name in tool_name_mapping
            ]
            agent = create_agent(config_with_tools)
        else:
            agent = create_agent(config)

        # Restore the memory and state
        if 'memory' in state:
            agent.memory = state['memory']

        # Restore other important state
        if 'step_number' in state:
            agent.step_number = state['step_number']
        if 'max_steps' in state:
            agent.max_steps = state['max_steps']
        if 'instructions' in state and state['instructions']:
            agent.instructions = state['instructions']

        return agent

    except Exception as e:
        logger.warning(f"Error deserializing agent state: {e}. Starting with fresh agent.")
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
        if agent_instance is None or config != agent_config or reset:
            # Fetch memory context if memory system is enabled (in async context)
            memory_context = None
            memory_enabled = config.get("memory_enabled", False)
            if memory_manager and memory_enabled:
                chat_id = config.get("_chat_id")
                user_id = config.get("_user_id", "default-user")
                try:
                    memory_context = await memory_manager.format_core_memory_for_context(
                        chat_id=chat_id,
                        user_id=user_id
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


def inject_chat_context(agent: CodeAgent, chat_id: str, user_id: str = None) -> None:
    """
    Inject chat context into agent tools that support it.

    Args:
        agent: The agent instance whose tools should receive context.
        chat_id: The chat identifier to inject into tools.
        user_id: The user identifier for memory system (defaults to CONFIG.user_id).
    """
    if not chat_id or not hasattr(agent, '_tool_instances'):
        return

    # Use configured user_id if not provided
    if user_id is None:
        from suzent.config import CONFIG
        user_id = CONFIG.user_id

    for tool_instance in agent._tool_instances:
        # Inject chat_id for tools like PlanningTool
        if hasattr(tool_instance, 'set_chat_context'):
            tool_instance.set_chat_context(chat_id)

        # Inject user_id and chat_id for memory tools
        if tool_instance.__class__.__name__ in ['MemorySearchTool', 'MemoryBlockUpdateTool']:
            if hasattr(tool_instance, 'set_context'):
                tool_instance.set_context(chat_id=chat_id, user_id=user_id)
