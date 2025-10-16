"""
Agent management module for creating, serializing, and managing agent state.

This module handles the lifecycle of AI agents including:
- Creating agents with specified configurations
- Serializing agent state for persistence
- Deserializing and restoring agent state
- Managing global agent instances
"""

import asyncio
import importlib
import pickle
from typing import Optional, Dict, Any

from smolagents import CodeAgent, LiteLLMModel, MCPClient
from smolagents.tools import Tool

from suzent.config import Config


# --- Agent State ---
agent_instance: Optional[CodeAgent] = None
agent_config: Optional[dict] = None
agent_lock = asyncio.Lock()


def create_agent(config: Dict[str, Any]) -> CodeAgent:
    """
    Creates an agent based on the provided configuration.
    
    Args:
        config: Configuration dictionary containing:
            - model: Model identifier (e.g., "gemini/gemini-2.5-pro")
            - agent: Agent type (e.g., "CodeAgent")
            - tools: List of tool names to enable
            - mcp_urls: Optional list of MCP server URLs
            - instructions: Optional custom instructions
    
    Returns:
        Configured CodeAgent instance with specified tools and model.
    
    Raises:
        ValueError: If an unknown agent type is specified.
    """
    model_id = config.get("model", "gemini/gemini-2.5-pro")
    agent_name = config.get("agent", "CodeAgent")
    # Use DEFAULT_TOOLS if tools not specified in config
    tool_names = config.get("tools", Config.DEFAULT_TOOLS)

    model = LiteLLMModel(model_id=model_id)

    tools = []
    
    # Mapping of tool class names to their module file names
    tool_module_map = {
        "WebSearchTool": "websearch_tool",
        "PlanningTool": "planning_tool",
        "WebpageTool": "webpage_tool",
        # Add other custom tools here as needed
    }
    
    custom_tool_names = tool_names

    for tool_name in custom_tool_names:
        try:
            module_file_name = tool_module_map.get(tool_name)
            if not module_file_name:
                print(f"Warning: No module mapping found for tool {tool_name}. Skipping.")
                continue

            tool_module = importlib.import_module(f"suzent.tools.{module_file_name}")
            # Get the tool class from the module
            tool_class = getattr(tool_module, tool_name)
            # Instantiate the tool if it's a subclass of Tool
            if issubclass(tool_class, Tool):
                tools.append(tool_class())
            else:
                print(f"Warning: {tool_name} is not a valid Tool class. Skipping.")
        except (ImportError, AttributeError) as e:
            print(f"Warning: Could not load tool {tool_name}: {e}")

    mcp_urls = config.get("mcp_urls", [])
    if mcp_urls:
        mcp_server_parameters = [
            {"url": url, "transport": "streamable-http"} for url in mcp_urls
        ]
        mcp_client = MCPClient(server_parameters=mcp_server_parameters)
        tools.extend(mcp_client.get_tools())

    agent_map = {
        "CodeAgent": CodeAgent,
    }

    agent_class = agent_map.get(agent_name)
    if not agent_class:
        raise ValueError(f"Unknown agent: {agent_name}")

    instructions = config.get("instructions", Config.INSTRUCTIONS)
    agent = agent_class(model=model, tools=tools, stream_outputs=True, instructions=instructions)
    # Store tool instances on the agent for later context injection
    agent._tool_instances = tools
    return agent


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

        serializable_state = {
            'memory': agent.memory,
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
        print(f"Error serializing agent: {e}")
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
        # Deserialize the state
        state = pickle.loads(agent_data)
        
        # Create a new agent with the same configuration
        # Use tool names from saved state to ensure consistency
        if 'tool_names' in state and state['tool_names']:
            # Map tool names back to config format
            tool_name_mapping = {
                'WebSearchTool': 'WebSearchTool',
                'PlanningTool': 'PlanningTool',
                'WebpageTool': 'WebpageTool',
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
        print(f"Error deserializing agent: {e}")
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
            agent_instance = create_agent(config)
            agent_config = config
        
        return agent_instance


def inject_chat_context(agent: CodeAgent, chat_id: str) -> None:
    """
    Inject chat context into agent tools that support it.
    
    Args:
        agent: The agent instance whose tools should receive context.
        chat_id: The chat identifier to inject into tools.
    """
    if not chat_id or not hasattr(agent, '_tool_instances'):
        return
    
    for tool_instance in agent._tool_instances:
        if hasattr(tool_instance, 'set_chat_context'):
            tool_instance.set_chat_context(chat_id)
