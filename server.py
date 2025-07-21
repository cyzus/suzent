from anyio import to_thread
from starlette.applications import Starlette
from starlette.responses import StreamingResponse
from starlette.routing import Route

from smolagents import CodeAgent, LiteLLMModel, MCPClient, WebSearchTool
from dotenv import load_dotenv
load_dotenv()
import types, re, json
from smolagents.models import ChatMessageStreamDelta
from smolagents.memory import FinalAnswerStep, ActionStep
from smolagents.agents import ActionOutput, PlanningStep
from dataclasses import asdict, is_dataclass, fields

# Create an MCP client to connect to the MCP server
mcp_server_parameters = {
    "url": "https://evalstate-hf-mcp-server.hf.space/mcp",
    "transport": "streamable-http",
}
mcp_client = MCPClient(server_parameters=mcp_server_parameters)
tools = mcp_client.get_tools()
# Create a CodeAgent with a specific model and the tools from the MCP client
agent = CodeAgent(
    model=LiteLLMModel(model_id="gemini/gemini-2.5-pro"),
    tools=[WebSearchTool()],
    stream_outputs=True,
)

# Helper to recursively convert objects to serializable dicts/lists

def to_serializable(obj):
    # Only call asdict on dataclass instances, not classes
    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in fields(obj):
            value = getattr(obj, f.name)
            # If the field is an exception, convert to string
            if isinstance(value, Exception):
                result[f.name] = str(value)
            else:
                result[f.name] = to_serializable(value)
        return result
    elif hasattr(obj, "dict") and not isinstance(obj, type):
        return obj.dict()
    elif isinstance(obj, Exception):
        # Serialize exceptions as strings
        return str(obj)
    elif hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {k: to_serializable(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    elif isinstance(obj, (list, tuple)):
        return [to_serializable(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, types.GeneratorType):
        return [to_serializable(i) for i in obj]
    else:
        return obj

# Define the shutdown handler to disconnect the MCP client
async def shutdown():
    mcp_client.disconnect()

async def chat(request):
    data = await request.json()
    message = data.get("message", "").strip()

    def step_to_json(chunk):
        if isinstance(chunk, ActionStep):
            return {"type": "action", "data": to_serializable(chunk)}
        elif isinstance(chunk, PlanningStep):
            return {"type": "planning", "data": to_serializable(chunk)}
        elif isinstance(chunk, FinalAnswerStep):
            output = getattr(chunk, 'output', str(chunk))
            serial = to_serializable(output)
            if isinstance(serial, (dict, list)) and not serial:
                serial = str(output)
            elif hasattr(output, 'to_string') and not isinstance(output, str):
                try:
                    serial = output.to_string()
                except Exception:
                    serial = str(output)
            elif not isinstance(serial, (str, int, float, bool, dict, list)):
                serial = str(output)
            return {"type": "final_answer", "data": serial}
        elif isinstance(chunk, ChatMessageStreamDelta):
            return {"type": "stream_delta", "data": to_serializable(chunk)}
        elif isinstance(chunk, ActionOutput):
            if chunk.output is None:
                return {}
            return {"type": "action_output", "data": to_serializable(chunk)}
        else:
            return {"type": "other", "data": str(chunk)}

    def stream_agent():
        try:
            result = agent.run(message, stream=True)
            if isinstance(result, types.GeneratorType):
                for chunk in result:
                    try:
                        json_chunk = step_to_json(chunk)
                        if json_chunk is None:
                            continue
                        json_str = json.dumps(json_chunk) + "\n"
                        yield json_str
                    except Exception as e:
                        error_str = json.dumps({"type": "error", "data": f"Serialization error: {str(e)} | Raw: {str(chunk)}"}) + "\n"
                        yield error_str
            else:
                json_str = json.dumps({"type": "result", "data": str(result)}) + "\n"
                yield json_str
        except Exception as e:
            error_str = json.dumps({"type": "error", "data": str(e)}) + "\n"
            yield error_str

    return StreamingResponse(stream_agent(), media_type="application/json")

app = Starlette(
    debug=True,
    routes=[
        Route("/chat", chat, methods=["POST"]),
    ],
    on_shutdown=[shutdown],  # Register the shutdown handler: disconnect the MCP client
)