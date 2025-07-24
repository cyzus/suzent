import os
import importlib
from pathlib import Path

class Config:
    # Application Configuration
    TITLE = "SUZ AGENT"
    SERVER_URL = "http://localhost:8000/chat"
    CODE_TAG = "<code>"

    # Model and Agent Options
    MODEL_OPTIONS = [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4.1",
        "deepseek/deepseek-chat"
    ]
    AGENT_OPTIONS = ["CodeAgent"]
    
    # --- Tool Configuration ---
    @staticmethod
    def get_tool_options():
        tools_dir = Path(__file__).parent / "tools"
        tool_options = []
        for f in os.listdir(tools_dir):
            if f.endswith(".py") and not f.startswith("__"):
                module_name = f"suzent.tools.{f[:-3]}"
                module = importlib.import_module(module_name)
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    # Check if it's a class, a subclass of Tool, and not Tool itself
                    if isinstance(attribute, type) and issubclass(attribute, object) and attribute.__name__ != "Tool" and attribute.__module__.startswith("suzent.tools"):
                        tool_options.append(attribute.__name__)
        return tool_options
    DEFAULT_TOOLS = ["WebSearchTool"]
    TOOL_OPTIONS = get_tool_options() + DEFAULT_TOOLS
    DEFAULT_MCP_URLS = "https://evalstate-hf-mcp-server.hf.space/mcp"

    # Example configuration options (can be removed if not used)
    DEBUG = True
    PORT = 8000
    HOST = "0.0.0.0"
    API_KEY = "your_api_key_here"

    # Add other configurations as needed