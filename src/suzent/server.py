"""
This module implements a Starlette-based web server to interact with a code-generating agent.

The server exposes a /chat endpoint that accepts POST requests with a JSON body
containing a "message" field. It streams back a series of server-sent events (SSEs)
representing the agent's thought process, actions, and final answer.
"""

import asyncio
import json
import os
import types
import pickle
import copy
from dataclasses import asdict, is_dataclass
from typing import Optional, Dict, Any
from json import JSONEncoder
import importlib
import contextlib

from dotenv import load_dotenv
from smolagents import CodeAgent, LiteLLMModel, MCPClient, WebSearchTool
from smolagents.agents import ActionOutput, PlanningStep
from smolagents.memory import ActionStep, FinalAnswerStep
from smolagents.models import ChatMessageStreamDelta
from smolagents.tools import Tool # Import the base Tool class
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse, JSONResponse
from starlette.routing import Route
from mcp import StdioServerParameters
from suzent.config import Config
from suzent.plan import read_plan_from_database, read_plan_history_from_database, plan_to_dict
from suzent.database import get_database, generate_chat_title

load_dotenv()

# --- Agent State ---
agent_instance: Optional[CodeAgent] = None
agent_config: Optional[dict] = None
agent_lock = asyncio.Lock()

# --- Agent Serialization ---
def serialize_agent(agent) -> Optional[bytes]:
    """
    Serialize an agent and its complete state to bytes.
    This preserves all memory, configuration, and internal state.
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


# --- Agent Configuration ---
def create_agent(config: Dict[str, Any]) -> CodeAgent:
    """
    Creates an agent based on the provided configuration.
    """
    model_id = config.get("model", "gemini/gemini-2.5-pro")
    agent_name = config.get("agent", "CodeAgent")
    # Use DEFAULT_TOOLS if tools not specified in config
    tool_names = config.get("tools", Config.DEFAULT_TOOLS)

    model = LiteLLMModel(model_id=model_id)

    tools = []
    if "WebSearchTool" in tool_names:
        tools.append(WebSearchTool())
    
    # Filter out WebSearchTool from tool_names for dynamic loading
    custom_tool_names = [t for t in tool_names if t != "WebSearchTool"]

    # Mapping of tool class names to their module file names
    tool_module_map = {
        "PlanningTool": "planning_tool",
        "WebpageTool": "webpage_tool",
        # Add other custom tools here as needed
    }

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


# --- JSON Serialization ---
class CustomJsonEncoder(JSONEncoder):
    """
    Custom JSON encoder to handle serialization of various object types,
    including dataclasses and exceptions.
    """

    def default(self, o):
        if is_dataclass(o):
            return asdict(o)
        if isinstance(o, Exception):
            return str(o)
        if hasattr(o, "dict"):
            return o.dict()
        if hasattr(o, "__dict__"):
            return {
                k: v
                for k, v in o.__dict__.items()
                if not k.startswith("_") and self._is_json_serializable(v)
            }
        if isinstance(o, types.GeneratorType):
            return list(o)
        return super().default(o)

    def _is_json_serializable(self, value):
        try:
            json.dumps(value)
            return True
        except (TypeError, OverflowError):
            return False


def to_serializable(obj):
    """
    Recursively converts an object to a JSON-serializable format.
    """
    return json.loads(json.dumps(obj, cls=CustomJsonEncoder))


# --- Event Stream Handling ---
def step_to_json_event(chunk):
    """
    Converts an agent's step into a JSON event dictionary.
    """
    event_map = {
        ActionStep: "action",
        PlanningStep: "planning",
        FinalAnswerStep: "final_answer",
        ChatMessageStreamDelta: "stream_delta",
        ActionOutput: "action_output",
    }
    event_type = next(
        (event_map[t] for t in event_map if isinstance(chunk, t)), "other"
    )

    if event_type == "final_answer":
        output = getattr(chunk, "output", str(chunk))
        data = (
            output.to_string()
            if hasattr(output, "to_string") and not isinstance(output, str)
            else str(output)
        )
    elif event_type == "action_output" and chunk.output is None:
        return None
    else:
        data = to_serializable(chunk)

    return {"type": event_type, "data": data}


def _plan_snapshot(chat_id: str = None):
    try:
        if not chat_id:
            return {"objective": "", "tasks": []}
        plan = read_plan_from_database(chat_id)
        if not plan:
            return {"objective": "", "tasks": []}
        return {
            "objective": plan.objective,
            "tasks": [
                {
                    "number": t.number,
                    "description": t.description,
                    "status": t.status,
                    "note": getattr(t, "note", None),
                }
                for t in plan.tasks
            ],
        }
    except Exception:
        return {"objective": "", "tasks": []}


async def stream_agent_responses(agent, message: str, reset: bool = False, chat_id: str = None):
    """Runs the agent with the given message and yields JSON-formatted SSE events.
    Uses a background thread + asyncio.Queue so the event loop is not blocked and
    deltas flush to the client sooner. Adds a plan file watcher to emit timely updates."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    class _PlanTick:
        __slots__ = ["snapshot"]
        def __init__(self, snapshot):
            self.snapshot = snapshot

    def worker():  # runs in thread
        try:
            gen = agent.run(message, stream=True, reset=reset)
            for chunk in gen:
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:  # propagate error
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel
            loop.call_soon_threadsafe(stop_event.set)

    async def plan_watcher(interval: float = 0.7):
        """Watch the plan file for changes and enqueue updates (no yields)."""
        last_snapshot = None
        try:
            while not stop_event.is_set():
                await asyncio.sleep(interval)
                try:
                    snapshot = _plan_snapshot(chat_id)
                    if snapshot != last_snapshot:
                        last_snapshot = snapshot
                        await queue.put(_PlanTick(snapshot))
                except Exception as e:
                    await queue.put(_PlanTick({"error": str(e)}))
        except asyncio.CancelledError:
            pass

    # Start worker thread and watcher task
    import threading
    threading.Thread(target=worker, daemon=True).start()
    watcher_task = asyncio.create_task(plan_watcher())

    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        if isinstance(chunk, Exception):
            error_event = {"type": "error", "data": str(chunk)}
            yield f"data: {json.dumps(error_event)}\n\n"
            continue
        # Handle plan watcher ticks before generic serialization
        if isinstance(chunk, _PlanTick):
            try:
                plan_event = {"type": "plan_refresh", "data": chunk.snapshot}
                yield f"data: {json.dumps(plan_event)}\n\n"
            except Exception as e:
                error_event = {"type": "error", "data": f"Plan tick error: {e!s}"}
                yield f"data: {json.dumps(error_event)}\n\n"
            await asyncio.sleep(0)
            continue
        try:
            json_event = step_to_json_event(chunk)
            if json_event:
                yield f"data: {json.dumps(json_event)}\n\n"
                et = json_event.get("type")
                if et in ("planning", "action"):
                    plan_event = {"type": "plan_refresh", "data": _plan_snapshot(chat_id)}
                    yield f"data: {json.dumps(plan_event)}\n\n"
        except Exception as e:
            error_event = {"type": "error", "data": f"Serialization error: {e!s} | Raw: {chunk!s}"}
            yield f"data: {json.dumps(error_event)}\n\n"
        await asyncio.sleep(0)  # allow loop to flush

    stop_event.set()
    watcher_task.cancel()
    with contextlib.suppress(Exception):
        await watcher_task
    
    # Save agent state after streaming completes (if we have a chat_id)
    if chat_id:
        try:
            agent_state = serialize_agent(agent)
            if agent_state:
                db = get_database()
                # Update the chat with the new agent state
                db.update_chat(chat_id, agent_state=agent_state)
        except Exception as e:
            print(f"Error saving agent state for chat {chat_id}: {e}")


# --- API Endpoint ---
async def chat(request):
    """
    Handles chat requests, streams agent responses, and manages the SSE stream.
    """
    global agent_instance, agent_config
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        reset = data.get("reset", False)
        config = data.get("config", {})
        chat_id = data.get("chat_id")  # New: get chat_id for context

        if not message:
            return StreamingResponse(
                iter(
                    [
                        'data: {"type": "error", "data": "Empty message received."}\n\n'
                    ]
                ),
                media_type="text/event-stream",
                status_code=400,
            )

        async def response_generator():
            global agent_instance, agent_config
            async with agent_lock:
                # Re-create agent if config changes or if it's not initialized
                if agent_instance is None or config != agent_config:
                    try:
                        agent_instance = create_agent(config)
                        agent_config = config
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        yield f'data: {{\"type\": \"error\", \"data\": \"Error creating agent: {e!s}\"}}\n\n'
                        return

                # If we have a chat_id and not resetting, try to restore agent state
                if chat_id and not reset:
                    try:
                        db = get_database()
                        chat = db.get_chat(chat_id)
                        
                        if chat:
                            agent_state = chat.get('agent_state')
                            
                            if agent_state:
                                restored_agent = deserialize_agent(agent_state, config)
                                if restored_agent:
                                    agent_instance = restored_agent
                    except Exception as e:
                        print(f"Error loading agent state: {e}")
                        # Continue without state restoration rather than failing

                # Inject chat_id into tools if available
                if chat_id and agent_instance and hasattr(agent_instance, '_tool_instances'):
                    for tool_instance in agent_instance._tool_instances:
                        if hasattr(tool_instance, 'set_chat_context'):
                            tool_instance.set_chat_context(chat_id)

                # Stream agent responses
                async for chunk in stream_agent_responses(agent_instance, message, reset=reset, chat_id=chat_id):
                    yield chunk
        
        return StreamingResponse(
            response_generator(),
            media_type="text/event-stream",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except json.JSONDecodeError:
        return StreamingResponse(
            iter(['data: {"type": "error", "data": "Invalid JSON."}\n\n']),
            media_type="text/event-stream",
            status_code=400,
        )
    except Exception as e:
        return StreamingResponse(
            iter([f'data: {{\"type\": \"error\", \"data\": \"An unexpected error occurred: {e!s}\"}}\n\n']),
            media_type="text/event-stream",
            status_code=500,
        )


async def get_config(request):
    """Return frontend-consumable configuration derived from Config class."""
    data = {
        "title": Config.TITLE,
        "models": Config.MODEL_OPTIONS,
        "agents": Config.AGENT_OPTIONS,
        "tools": Config.TOOL_OPTIONS,
        "defaultTools": Config.DEFAULT_TOOLS,
        "codeTag": Config.CODE_TAG,
    }
    return JSONResponse(data)

async def get_plan(request):
    """Return the current plan and historical versions for a chat."""
    try:
        chat_id = request.query_params.get("chat_id")
        if not chat_id:
            return JSONResponse({"error": "chat_id parameter is required"}, status_code=400)

        current_plan = plan_to_dict(read_plan_from_database(chat_id))
        history_plans = [plan_to_dict(p) for p in read_plan_history_from_database(chat_id)]

        # Exclude the current plan from history list if duplicated
        if current_plan:
            current_id = current_plan.get("id")
            current_key = current_plan.get("versionKey")
            pruned: list[dict] = []
            for p in history_plans:
                if not p:
                    continue
                if current_id is not None and p.get("id") == current_id:
                    continue
                if current_key and p.get("versionKey") == current_key:
                    continue
                pruned.append(p)
            history_plans = pruned
        else:
            history_plans = [p for p in history_plans if p]

        return JSONResponse({
            "current": current_plan,
            "history": history_plans,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_chats(request):
    """Return list of chat summaries."""
    try:
        db = get_database()
        
        # Parse query parameters
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
        
        chats = db.list_chats(limit=limit, offset=offset)
        total = db.get_chat_count()
        
        return JSONResponse({
            "chats": chats,
            "total": total,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_chat(request):
    """Return a specific chat by ID."""
    try:
        chat_id = request.path_params["chat_id"]
        db = get_database()
        
        chat = db.get_chat(chat_id)
        if not chat:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        
        # Remove agent_state from response as it's binary data not needed by frontend
        response_chat = {k: v for k, v in chat.items() if k != 'agent_state'}
        
        return JSONResponse(response_chat)
    except Exception as e:
        print(f"Error in get_chat: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def create_chat(request):
    """Create a new chat."""
    try:
        data = await request.json()
        title = data.get("title", "New Chat")
        config = data.get("config", {})
        messages = data.get("messages", [])
        
        db = get_database()
        chat_id = db.create_chat(title, config, messages)
        
        # Return the created chat (excluding binary agent_state)
        chat = db.get_chat(chat_id)
        if chat:
            response_chat = {k: v for k, v in chat.items() if k != 'agent_state'}
            return JSONResponse(response_chat, status_code=201)
        else:
            return JSONResponse({"error": "Failed to create chat"}, status_code=500)
    except Exception as e:
        print(f"Error in create_chat: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def update_chat(request):
    """Update an existing chat."""
    try:
        chat_id = request.path_params["chat_id"]
        data = await request.json()
        
        db = get_database()
        
        # Extract update fields
        title = data.get("title")
        config = data.get("config")
        messages = data.get("messages")
        
        success = db.update_chat(chat_id, title=title, config=config, messages=messages)
        if not success:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        
        # Return updated chat (excluding binary agent_state)
        chat = db.get_chat(chat_id)
        if chat:
            response_chat = {k: v for k, v in chat.items() if k != 'agent_state'}
            return JSONResponse(response_chat)
        else:
            return JSONResponse({"error": "Failed to retrieve updated chat"}, status_code=500)
    except Exception as e:
        print(f"Error in update_chat: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def delete_chat(request):
    """Delete a chat."""
    try:
        chat_id = request.path_params["chat_id"]
        db = get_database()
        
        success = db.delete_chat(chat_id)
        if not success:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        
        return JSONResponse({"message": "Chat deleted successfully"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# --- Application Setup ---
app = Starlette(
    debug=True,
    routes=[
        Route("/chat", chat, methods=["POST"]),
        Route("/config", get_config, methods=["GET"]),
        Route("/plan", get_plan, methods=["GET"]),
        Route("/chats", get_chats, methods=["GET"]),
        Route("/chats", create_chat, methods=["POST"]),
        Route("/chats/{chat_id}", get_chat, methods=["GET"]),
        Route("/chats/{chat_id}", update_chat, methods=["PUT"]),
        Route("/chats/{chat_id}", delete_chat, methods=["DELETE"]),
    ],
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)