# Suzent Tools Guide

This guide covers all the tools available in Suzent and how to use them effectively.

## Overview

Suzent tools extend the capabilities of AI agents, allowing them to interact with external services and perform specialized tasks. Each tool is a self-contained module that can be enabled or disabled in the agent configuration.

## Available Tools

### 1. WebSearchTool

Performs web searches using either SearXNG (privacy-focused) or the default smolagents search engine.

**Features:**
- Privacy-focused meta-search via SearXNG
- Automatic fallback to default search if SearXNG unavailable
- Clean markdown-formatted results
- Configurable search parameters (categories, language, time range)

**Usage:**
```python
from suzent.tools.websearch_tool import WebSearchTool

tool = WebSearchTool()
results = tool.forward("your search query")
```

**Configuration:**

To use SearXNG, set in your `.env`:
```bash
SEARXNG_BASE_URL=http://localhost:2077
```

Without this setting, the tool automatically uses the default smolagents search.

**Parameters:**
- `query` (required): The search query string
- `categories` (optional): Search categories (e.g., 'general', 'news', 'images') - SearXNG only
- `language` (optional): Language code (e.g., 'en', 'fr') - SearXNG only
- `time_range` (optional): Time filter ('day', 'week', 'month', 'year') - SearXNG only
- `page` (optional): Page number for results (default: 1) - SearXNG only

**Output Format:**

Results are formatted as markdown with:
- Numbered search results (top 10)
- Clear titles and URLs
- Content snippets (truncated to 200 chars)
- Source engines listed

Example output:
```markdown
# Search Results for: python tutorials

## 1. Python Tutorial - Official Documentation
**URL:** https://docs.python.org/3/tutorial/
**Description:** The Python Tutorial — Python 3.x documentation. This tutorial introduces the reader informally to the basic concepts and features of the Python language...
**Sources:** google, duckduckgo, brave

## 2. Learn Python Programming
**URL:** https://www.learnpython.org/
**Description:** Learn Python with interactive tutorials and examples. Start with the basics and progress to advanced topics...
**Sources:** bing, duckduckgo
```

**Setup:**

For SearXNG setup, see the [SearXNG Setup Guide](searxng-setup.md).

---

### 2. PlanningTool

Helps agents create and manage structured plans for complex tasks.

**Features:**
- Break down complex tasks into steps
- Track plan progress
- Store and retrieve plans from the database


**Context Injection:**

The PlanningTool supports chat context injection to associate plans with specific conversations:

```python
tool.set_chat_context(chat_id="abc123")
```

This is automatically handled by the agent manager.

---

### 3. WebpageTool

Retrieves and processes content from web pages.

**Features:**
- Fetch web page content
- Extract text and relevant information
- Handle different content types

**Usage:**
```python
from suzent.tools.webpage_tool import WebpageTool

tool = WebpageTool()
content = tool.forward("https://example.com")
```

### 4. File Tools

Foundational tools for filesystem interaction. These operate on the local filesystem by default, or inside the secure sandbox if **Sandbox Execution** is enabled.

- **`ReadFileTool`**: Reads content from a file.
- **`WriteFileTool`**: Creates or overwrites a file.
- **`EditFileTool`**: Replaces specific chunks of text in a file (powered by unified diffs).
- **`GlobTool`**: Finds files matching a pattern (e.g., `src/**/*.py`).
- **`GrepTool`**: Searches regular expressions within files.

**Usage:**
```python
from suzent.tools.read_file_tool import ReadFileTool
content = ReadFileTool().forward("/path/to/file.txt")
```

---

### 5. BashTool (Sandbox)

Executes bash commands safely. This tool is **only** available when the agent is running in Sandbox mode. It runs commands inside the isolated Firecracker MicroVM, ensuring no harm to the host system.

**Features:**
- Persistent session state (current working directory, variables)
- Access to mounted volumes and persisted data
- Timeout and output truncation safety

**Usage:**
```python
from suzent.tools.bash_tool import BashTool
# Initialize (typically done by agent manager)
tool = BashTool()
result = tool.forward("ls -la /workspace")
```

---

## Configuring Tools

### In Agent Configuration

Tools are configured in the agent configuration. You can enable/disable tools by specifying them in your config:

```python
config = {
    "model": "gemini/gemini-2.5-pro",
    "agent": "CodeAgent",
    "tools": [
        "WebSearchTool",
        "PlanningTool",
        "ReadFileTool", 
        "EditFileTool"
    ]
}
```

### Default Tools

If not specified, Suzent uses the default tools defined in `src/suzent/config.py`:

```python
DEFAULT_TOOLS = [
    "WebSearchTool",
    "PlanningTool",
    "WebpageTool",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "GlobTool",
    "GrepTool"
]
```

---

## Tool Best Practices

### For Users

1. **Choose the right tool** - Understand what each tool does and when to use it
2. **Configure properly** - Ensure environment variables are set correctly
3. **Check logs** - Tool initialization messages appear in server logs
4. **Test separately** - Test tools individually before using in agents

### For Developers

1. **Clear descriptions** - Help the agent understand when to use the tool
2. **Type hints** - Use proper Python type hints for better IDE support
3. **Error handling** - Always handle errors gracefully and return informative messages
4. **Documentation** - Include docstrings for all methods
5. **Testing** - Create tests for your tools

---

## Creating Custom Tools

Quick overview:

1. Create a new file in `src/suzent/tools/` (e.g., `my_tool.py`)
2. Inherit from `Tool` base class
3. Define inputs and outputs
4. Implement the `forward()` method
5. Register in `agent_manager.py`

Example:

```python
from smolagents.tools import Tool

class MyCustomTool(Tool):
    name: str = "MyCustomTool"
    description: str = "Does something useful"
    
    inputs = {
        "param1": {
            "type": "string",
            "description": "Parameter description"
        }
    }
    output_type = "string"
    
    def forward(self, param1: str) -> str:
        # Your logic here
        return f"Processed: {param1}"
```

---

## Troubleshooting

### WebSearchTool Issues

**Problem:** "Error: Failed to connect to SearXNG"

**Solution:**
1. Check if SearXNG is running: `docker-compose ps`
2. Verify SEARXNG_BASE_URL in `.env`
3. Test connectivity: `curl http://localhost:2077/search?q=test&format=json`
4. The tool will automatically fall back to default search if SearXNG is unavailable

**Problem:** "403 Forbidden" error

**Solution:**
1. Check SearXNG settings.yml has `limiter: false`
2. Ensure `formats` includes `json` in settings.yml
3. Restart SearXNG: `docker-compose restart searxng`

### PlanningTool Issues

**Problem:** Plans not saving

**Solution:**
1. Check database connection
2. Verify chat context is set properly
3. Check server logs for database errors

### General Tool Issues

**Problem:** Tool not found or not loading

**Solution:**
1. Verify tool name in configuration matches exactly
2. Check tool is registered in `agent_manager.py`
3. Review server startup logs for import errors
4. Ensure all dependencies are installed

---

## Performance Tips

1. **SearXNG** - Self-hosted search is faster than external APIs
2. **Caching** - SearXNG caches results in Redis for better performance
3. **Rate limiting** - Consider rate limits when using external APIs
4. **Parallel requests** - Some tools can make parallel requests for better performance

---

## Resources

- [smolagents Documentation](https://github.com/huggingface/smolagents)
- [SearXNG Documentation](https://docs.searxng.org/)
