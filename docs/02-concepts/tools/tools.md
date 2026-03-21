# Tools

Tools extend the agent's capabilities, allowing it to interact with the filesystem, web, memory, social platforms, and more. Each tool is a **function** registered on the pydantic-ai `Agent` via the tool registry.

## Architecture

Suzent uses [pydantic-ai](https://ai.pydantic.dev/) for its agent framework. Tools are plain Python functions (sync or async) — not classes. Tools that need per-request state (sandbox config, file paths, memory) receive it via **dependency injection** through `RunContext[AgentDeps]`.

```
Agent
 ├── tools: [web_search, read_file, bash_execute, ...]   ← function-based
 ├── toolsets: [MCPServerStdio(...), ...]                 ← MCP servers
 └── deps_type: AgentDeps                                 ← shared context
```

### AgentDeps

All per-session context lives in a single `AgentDeps` dataclass, injected into every tool that needs it:

```python
@dataclass
class AgentDeps:
    chat_id: str                  # Current conversation ID
    user_id: str                  # Current user
    sandbox_enabled: bool         # Whether sandbox mode is active
    workspace_root: str           # Root path for file operations
    path_resolver: PathResolver   # Resolves relative paths safely
    memory_manager: MemoryManager # Long-term memory system
    channel_manager: Any          # Social messaging channels
    skill_manager: Any            # User-defined skills
    a2ui_queue: asyncio.Queue     # Canvas UI event queue (render_ui)
    # ... plus HITL fields (see Human-in-the-Loop doc)
```

Tools that are **stateless** (e.g. `web_search`, `webpage_fetch`) omit `RunContext` entirely — they're plain functions with no dependency injection.

## Available Tools

### Web & Search

| Tool | Function | Context | Description |
|------|----------|---------|-------------|
| WebSearchTool | `web_search` | — | Web search via SearXNG or DuckDuckGo |
| WebpageTool | `webpage_fetch` | — | Fetch and extract webpage content as markdown |
| BrowsingTool | `browser_action` | — | Control a headless browser (Playwright) |

### Filesystem

| Tool | Function | Context | HITL | Description |
|------|----------|---------|------|-------------|
| ReadFileTool | `read_file` | PathResolver | — | Read file contents (text, PDF, DOCX, images via OCR) |
| WriteFileTool | `write_file` | PathResolver | **Yes** | Create or overwrite files |
| EditFileTool | `edit_file` | PathResolver | **Yes** | Find-and-replace text in files |
| GlobTool | `glob_search` | PathResolver | — | Find files matching glob patterns |
| GrepTool | `grep_search` | PathResolver | — | Search file contents with regex |

### Execution

| Tool | Function | Context | HITL | Description |
|------|----------|---------|------|-------------|
| BashTool | `bash_execute` | Sandbox config | **Yes** | Execute code/commands (Python, Node.js, shell) |

### Planning & Memory

| Tool | Function | Context | Description |
|------|----------|---------|-------------|
| PlanningTool | `planning_update` | chat_id | Create and manage structured task plans |
| MemorySearchTool | `memory_search` | MemoryManager | Semantic search over long-term memory |
| MemoryBlockUpdateTool | `memory_block_update` | MemoryManager | Update core memory blocks (persona, user, facts, context) |

### Canvas & UI

| Tool | Function | Context | Description |
|------|----------|---------|-------------|
| RenderUITool | `render_ui` | a2ui_queue | Render interactive UI surfaces (tables, forms, cards, buttons) in the sidebar canvas or inline in chat |

See [Canvas (A2UI)](./canvas.md) for full documentation.

### Social & Output

| Tool | Function | Context | HITL | Description |
|------|----------|---------|------|-------------|
| SocialMessageTool | `social_message` | ChannelManager | **Yes** (sends only) | Send messages to Telegram, Discord, Slack, Feishu |
| SpeakTool | `speak` | — | — | Text-to-speech output |
| SkillTool | `skill_execute` | SkillManager | — | Execute user-defined skills |

**HITL** = Requires human approval before execution. See [Human-in-the-Loop](./human-in-the-loop.md).

## Tool Details

### `web_search`

Performs web searches using SearXNG (self-hosted, privacy-focused) with automatic fallback to DuckDuckGo.

**Parameters:**
- `query` (required): Search query string
- `categories`: Search category — `general`, `news`, `images`, `videos`
- `max_results`: Max results to return (default 10, max 20)
- `time_range`: Time filter — `day`, `week`, `month`, `year`
- `page`: Pagination (default 1)

**Configuration:** Set `SEARXNG_BASE_URL` in `.env` for SearXNG. Without it, falls back to DuckDuckGo.

### `bash_execute`

Executes code in a secure environment. Runs inside an isolated Docker container when sandbox mode is enabled, or on the host when disabled.

**Parameters:**
- `content` (required): Code or shell command to execute
- `language`: `python`, `nodejs`, or `command`
- `timeout`: Execution timeout in seconds

**Storage paths** (available in both modes):
- `/persistence` — Private storage, persists across sessions (current chat only)
- `/shared` — Shared storage, accessible by all chats

**Requires approval** — the user must Allow/Always Allow before execution.

### `read_file`

Reads file content with format-aware extraction.

**Supported formats:**
- Text files: `.txt`, `.py`, `.js`, `.json`, `.md`, `.csv`, etc.
- Documents: `.pdf`, `.docx`, `.xlsx`, `.pptx` (converted to markdown)
- Images: `.jpg`, `.png` (OCR text extraction)

**Parameters:**
- `file_path` (required): Path to the file
- `offset`: Line number to start from (0-indexed)
- `limit`: Number of lines to read

### `write_file` / `edit_file`

File creation and modification tools.

- `write_file`: Creates or overwrites a file. Creates parent directories automatically.
- `edit_file`: Find-and-replace within a file. Supports `replace_all` for bulk replacements.

Both **require approval** before execution.

### `glob_search` / `grep_search`

Filesystem search tools.

- `glob_search(pattern, path)`: Find files matching glob patterns (e.g. `**/*.py`)
- `grep_search(pattern, path, include, case_insensitive, context_lines)`: Regex search through file contents

### `planning_update`

Creates and manages structured plans for multi-step tasks. See [Planning Tool](./planning_tool.md) for detailed documentation.

### `memory_search` / `memory_block_update`

Long-term memory tools. See [Memory](../memory/README.md) for the full memory architecture.

- `memory_search(query, limit)`: Semantic similarity search over archived memories
- `memory_block_update(block, operation, content)`: Update always-visible core memory blocks (`persona`, `user`, `facts`, `context`)

### `social_message`

Send messages to social platforms or list available contacts.

- Listing contacts (`list_contacts=True`) does **not** require approval
- Sending messages **requires approval**

See [Social Messaging](../social-messaging/README.md) for platform setup.

### `browser_action`

Control a headless browser via Playwright.

**Commands:** `open`, `snapshot`, `click`, `fill`, `scroll`, `back`, `forward`, `reload`, `press`, `screenshot`, `click_coords`

### `speak`

Text-to-speech output. Converts text to audio and plays it.

### `skill_execute`

Execute user-defined skills. See [Skills](../skills/skills.md).

## Configuring Tools

### Default Tools

If not specified, the agent uses these tools (from `config.py`):

```
WebSearchTool, PlanningTool, ReadFileTool, WriteFileTool,
EditFileTool, GlobTool, GrepTool, BashTool
```

### Custom Tool Selection

Specify tools in the agent configuration:

```python
config = {
    "model": "gemini/gemini-2.5-pro",
    "tools": [
        "WebSearchTool",
        "PlanningTool",
        "ReadFileTool",
        "BashTool",
        "MemorySearchTool",
    ]
}
```

Tool names use the legacy class-name format (e.g. `"WebSearchTool"`) for backward compatibility with existing configs.

## Creating Custom Tools

To add a new tool:

1. **Create the tool function** in `src/suzent/tools/tool_functions.py`:

```python
from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps

def my_tool(
    ctx: RunContext[AgentDeps],  # omit if stateless
    param1: str,
    param2: int = 10,
) -> str:
    """Short description of what this tool does.

    Args:
        param1: Description of param1.
        param2: Description of param2.
    """
    # Your logic here
    return f"Result: {param1}"
```

2. **Register it** in the `TOOL_FUNCTIONS` dict at the bottom of `tool_functions.py`:

```python
TOOL_FUNCTIONS = {
    # ... existing tools ...
    "MyTool": my_tool,
}
```

3. **Add to defaults** (optional) in `config.py` if it should be enabled by default.

### Guidelines

- Use **Google-style docstrings** — pydantic-ai generates the tool schema from type hints + docstring
- Use `RunContext[AgentDeps]` as the first parameter only if the tool needs session context
- Async tools (`async def`) are preferred for I/O operations
- If the tool is dangerous (writes, executes, sends), add HITL approval — see [Human-in-the-Loop](./human-in-the-loop.md)
- Return informative error messages as strings (don't raise exceptions)

## Tool Registry

The tool registry (`src/suzent/tools/registry.py`) provides programmatic access:

```python
from suzent.tools.registry import get_tool_function, list_available_tools

# Get a specific tool function
fn = get_tool_function("WebSearchTool")

# List all available tool names
names = list_available_tools()
```
