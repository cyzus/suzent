# src/config.py

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
    TOOL_OPTIONS = ["WebSearchTool"]
    DEFAULT_TOOLS = ["WebSearchTool"]
    DEFAULT_MCP_URLS = "https://evalstate-hf-mcp-server.hf.space/mcp"

    # Example configuration options (can be removed if not used)
    DEBUG = True
    PORT = 8000
    HOST = "0.0.0.0"
    API_KEY = "your_api_key_here"

    # Add other configurations as needed