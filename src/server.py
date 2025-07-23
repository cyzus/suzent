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
from dataclasses import asdict, is_dataclass
from json import JSONEncoder

from dotenv import load_dotenv
from smolagents import CodeAgent, LiteLLMModel, WebSearchTool, MCPClient
from smolagents.agents import ActionOutput, PlanningStep
from smolagents.memory import ActionStep, FinalAnswerStep
from smolagents.models import ChatMessageStreamDelta
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from starlette.routing import Route
from mcp import StdioServerParameters

load_dotenv()

# --- Agent Configuration ---
def create_agent(config: dict):
    """
    Creates an agent based on the provided configuration.
    """
    model_id = config.get("model", "gemini/gemini-2.5-pro")
    agent_name = config.get("agent", "CodeAgent")
    tool_names = config.get("tools", ["WebSearchTool"])

    model = LiteLLMModel(model_id=model_id)

    tools = []
    if "WebSearchTool" in tool_names:
        tools.append(WebSearchTool())

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

    return agent_class(model=model, tools=tools, stream_outputs=True)


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


async def stream_agent_responses(agent, message: str, reset: bool = False):
    """
    Runs the agent with the given message and yields JSON-formatted server-sent events.
    """
    try:
        result_generator = await asyncio.to_thread(
            agent.run, message, stream=True, reset=reset
        )

        if isinstance(result_generator, types.GeneratorType):
            for chunk in result_generator:
                try:
                    json_event = step_to_json_event(chunk)
                    if json_event:
                        yield f"data: {json.dumps(json_event)}\n\n"
                except Exception as e:
                    error_event = {
                        "type": "error",
                        "data": f"Serialization error: {e!s} | Raw: {chunk!s}",
                    }
                    yield f"data: {json.dumps(error_event)}\n\n"
        else:
            result_event = {"type": "result", "data": str(result_generator)}
            yield f"data: {json.dumps(result_event)}\n\n"

    except Exception as e:
        error_event = {"type": "error", "data": str(e)}
        yield f"data: {json.dumps(error_event)}\n\n"


# --- API Endpoint ---
async def chat(request):
    """
    Handles chat requests, streams agent responses, and manages the SSE stream.
    """
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        reset = data.get("reset", False)
        config = data.get("config", {})

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
        
        agent = create_agent(config)

        return StreamingResponse(
            stream_agent_responses(agent, message, reset=reset),
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


# --- Application Setup ---
app = Starlette(
    debug=True,
    routes=[
        Route("/chat", chat, methods=["POST"]),
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