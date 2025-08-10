import os
import importlib
from pathlib import Path

# Graceful import of smolagents Tool base class
try:
    from smolagents import Tool as _SmolTool  # type: ignore
except ImportError:  # Fallback so config import does not fail in environments without smolagents installed yet
    class _SmolTool:  # type: ignore
        pass

class Config:
    # Application Configuration
    TITLE = "SUZ AGENT"
    SERVER_URL = "http://localhost:8000/chat"
    CODE_TAG = "<code>"

    # Model and Agent Options
    MODEL_OPTIONS = [
        "anthropic/claude-sonnet-4-20250514",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
        "openai/gpt-4.1",
        "deepseek/deepseek-chat"
    ]
    AGENT_OPTIONS = ["CodeAgent"]
    
    # --- Tool Configuration ---
    @staticmethod
    def get_tool_options():
        tools_dir = Path(__file__).parent / "tools"
        tool_options = []
        if not tools_dir.exists():
            return tool_options
        for f in os.listdir(tools_dir):
            if f.endswith(".py") and not f.startswith("__"):
                module_name = f"suzent.tools.{f[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                except Exception:
                    continue
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if (
                        isinstance(attribute, type)
                        and issubclass(attribute, _SmolTool)
                        and attribute is not _SmolTool
                        and getattr(attribute, "__module__", "").startswith("suzent.tools")
                    ):
                        tool_options.append(attribute.__name__)
        return tool_options

    DEFAULT_TOOLS = ["WebSearchTool", "PlanningTool"]

    # Deduplicate while preserving order (discovered first, then defaults appended if absent)
    _DISCOVERED = get_tool_options.__func__()  # call static without binding
    TOOL_OPTIONS = list(dict.fromkeys(_DISCOVERED + DEFAULT_TOOLS))

    DEFAULT_MCP_URLS = "https://evalstate-hf-mcp-server.hf.space/mcp"
