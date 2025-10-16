# Suzent Tools

This directory contains custom tools that extend the capabilities of Suzent agents.

## 📚 Documentation

For comprehensive documentation on tools, please see:

- **[Tools Guide](../../../docs/tools.md)** - Complete guide to all available tools
- **[SearXNG Setup](../../../docs/searxng-setup.md)** - Detailed SearXNG installation guide
- **[Development Guide](../../../docs/development.md)** - Creating custom tools

## 🛠️ Available Tools

### WebSearchTool
Privacy-focused web search using SearXNG or default search engine.
- **File:** `websearch_tool.py`
- **Setup:** See [SearXNG Setup Guide](../../../docs/searxng-setup.md)

### PlanningTool
Create and manage structured plans for complex tasks.
- **File:** `planning_tool.py`

### WebpageTool
Retrieve and process web page content.
- **File:** `webpage_tool.py`

## 🚀 Quick Start

### Using Tools

Tools are automatically loaded based on your agent configuration. Enable them in your config:

```python
config = {
    "tools": [
        "WebSearchTool",
        "PlanningTool",
        "WebpageTool"
    ]
}
```

### Creating Custom Tools

1. Create a new file in this directory (e.g., `my_tool.py`)
2. Inherit from `smolagents.tools.Tool`
3. Implement required methods
4. Register in `agent_manager.py`

See the [Development Guide](../../../docs/development.md) for detailed instructions.

## 📖 Learn More

- [Complete Tools Documentation](../../../docs/tools.md)
- [SearXNG Setup Guide](../../../docs/searxng-setup.md)
- [Configuration Guide](../../../docs/configuration.md)
- [Main Documentation](../../../docs/README.md)

