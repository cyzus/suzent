---
sidebar_position: 1
title: Tool system
---

# Tool system

This page is for contributors. For what tools do from a user's point of view, see
[Tools](../../03-features/tools/tools.md).

Tools extend the agent's capabilities, allowing it to interact with the filesystem, web, memory, social platforms, and more. Each tool is a function owned by a named capability in the centralized registry.

## Architecture

Suzent uses [pydantic-ai](https://ai.pydantic.dev/) for its agent framework. Registry classes provide metadata and typed functions. Selected functions are bundled into Pydantic AI capabilities; tools that need per-request state receive it through `RunContext[AgentDeps]`.

```
Agent
 ├── capabilities
 │    ├── filesystem: [read_file, write_file, ...]
 │    ├── shell: [run_command, start_command, ...]
 │    └── web: [web_search, webpage_fetch, ...]
 ├── toolsets: [MCPServerStdio(...), ...]                 ← MCP servers
 │    └── _deferred_toolset (per_run_step=True)           ← AI-activated tools
 └── deps_type: AgentDeps                                 ← shared context
```

The configuration API exposes the same capability catalog to the frontend,
including capability descriptions and each tool's display name, description,
runtime function name, and approval requirement. Capability headers toggle a
whole category, while every tool remains independently selectable.

### Deferred (AI-Activated) Tools

Not all tools need to be loaded at session start. The agent can call `tool_search` mid-conversation to activate additional tools on demand. Activated tools are injected into the agent's toolset before each LLM step via a `@agent.toolset` with `per_run_step=True`, and persist for the rest of the session.

Tools opt out of deferral by setting `deferrable = False` on their class (e.g. `MemorySearchTool`, `SkillTool`, `SocialMessageTool` — always-on internals that the agent shouldn't re-activate).

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
    base_tool_names: frozenset    # User-selected tools for this session (used by tool_search)
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

### Shell

| Tool | Function | Context | HITL | Description |
|------|----------|---------|------|-------------|
| RunCommandTool | `run_command` | Sandbox config | **Yes** | Run bounded commands and wait for their output |
| StartCommandTool | `start_command` | Sandbox config | **Yes** | Start a long-running background command |
| CheckCommandTool | `check_command` | Process registry | **Yes** | Read incremental output and command status |
| StopCommandTool | `stop_command` | Process registry | **Yes** | Stop a background command and clean up resources |

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

### Agent & Meta

| Tool | Function | Context | Description |
|------|----------|---------|-------------|
| ToolSearchTool | `tool_search` | AgentDeps | Discover and activate additional tools mid-conversation |
| AgentTool | `agent` | chat_id | Start a bounded sub-agent in the foreground or background |
| AgentListTool | `agent_list` | chat_id | List local project sessions and paired remote Suzent agents |
| AgentReadTool | `agent_read` | chat_id | Read one accessible agent's bounded visible transcript |
| AgentSendTool | `agent_send` | chat_id | Persist a message and wake another agent-backed session |
| AgentStopTool | `agent_stop` | chat_id | Stop one accessible active agent |

The lifecycle tools are intentionally separate instead of using one action-heavy
management schema. `agent_list` defaults to active tasks and caps results at 20;
recent results cap at 50. Agent IDs are stable chat IDs. Access is inferred from
the current project for local sessions; paired devices use stable `peer:`
addresses. Callers do not pass parent chat or project identifiers.
`agent_read` applies an internal transcript budget and returns the newest visible
messages when a conversation is large. `agent_send` has only two parameters
(`agent_id` and `message`): it writes to the durable agent inbox, returns after
the message is queued, and a background dispatcher wakes the target session.
Paired Suzent backends appear as `peer:<peer_id>` agents and use the same tool
schemas; their messages remain durable while the peer is temporarily offline.
Selecting `AgentTool` automatically equips these lifecycle operations as its
management dependencies. Sub-agents themselves cannot use the lifecycle tools,
which prevents unbounded recursive orchestration.

See [Agent Communication](./agent-inbox.md) for inbox delivery,
idempotency, and cross-device boundaries.

**HITL** = Requires human approval before execution. See [Human-in-the-Loop](../../03-features/tools/human-in-the-loop.md).

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

### Shell capability

Executes shell commands in a secure environment. Runs inside an isolated Docker container when sandbox mode is enabled, or on the host when disabled.

**Parameters:**
- `content` (required): Shell command to execute
- `run_command`: run bounded work synchronously with an optional timeout
- `start_command`: start a long-running command and return a command ID
- `check_command`: read incremental output and check completion
- `stop_command`: terminate the command and its process tree

Background commands continue after the agent finishes a turn. While the backend
is running, command completion or failure sends a durable inbox message to the
owning agent: an active turn receives the result in place, and an idle agent
starts a new background turn. Results include the exit code and the last 8,000
characters of output. `check_command` remains available for retained output.
A completed result already read by `check_command`, or a command explicitly
stopped with `stop_command` or the sidebar, does not trigger another wakeup.

The **Background tasks** sidebar combines sub-agents and Shell commands. It shows
live status, recent command output, exit codes, and stop controls. Command tracking
and recent sidebar history are in memory; they are not restored after a backend
restart. Once queued, completion messages use the existing durable agent inbox.

All four operations belong to the Shell capability and can be enabled separately.
Selecting a capability header in the frontend toggles every tool in that capability.
Existing `ShellTool`, `BashTool`, or `ProcessTool` selections are expanded to all
four operations during migration.

**Storage paths** (available in both modes):
- `/persistence` — Private storage, persists across sessions (current chat only)
- `/shared` — Shared storage, accessible by all chats

**Permission controlled** — execution is evaluated by the active permission mode,
shell policy, and persisted rules. It may run, be denied, or show backend-provided
approval actions.

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

Both are **permission controlled**. Default mode asks before writes, Auto mode
allows deterministic low-risk edits or escalates unresolved cases, and Full
Access removes ordinary approval prompts while preserving hard path and deny
checks.

### `glob_search` / `grep_search`

Filesystem search tools.

- `glob_search(pattern, path)`: Find files matching glob patterns (e.g. `**/*.py`)
- `grep_search(pattern, path, include, case_insensitive, context_lines)`: Regex search through file contents

### `planning_update`

Creates and manages structured plans for multi-step tasks. Plans are stored in the database and visualized in the frontend sidebar.

**Parameters:**
- `action`: `update` (create/overwrite a plan) or `advance` (mark a phase complete)
- `goal`: High-level goal description (required for `update`)
- `phases`: List of phases, each with `id`, `title`, `capabilities` (required for `update`)
- `current_phase_id`: Phase being completed (required for `advance`)
- `next_phase_id`: Phase to start next (required for `advance`)

**`action='update'`** — Creates a new plan or overwrites the existing one. Resets all progress: first phase becomes `in_progress`, all others `pending`.

**`action='advance'`** — Marks `current_phase_id` as `completed` and `next_phase_id` as `in_progress`. If `next_phase_id` skips phases, all intermediate phases are auto-completed.

### `memory_search` / `memory_block_update`

Long-term memory tools. See [Memory](../../03-features/memory/README.md) for the full memory architecture.

- `memory_search(query, limit)`: Semantic similarity search over archived memories
- `memory_block_update(block, operation, content)`: Update always-visible core memory blocks (`persona`, `user`, `facts`, `context`)

### `social_message`

Send messages to social platforms or list available contacts.

- Listing contacts (`list_contacts=True`) does **not** require approval
- Sending messages **requires approval**

See [Social Messaging](../../05-chat-apps/README.md) for platform setup.

### `browser_action`

Control your existing Chrome/Edge tabs and logins through the Suzent browser extension, or use a managed Playwright browser with optional persistent profiles. Direct CDP attachment remains an advanced option. All modes use the native tool; MCP is optional. See [Browser](../../03-features/tools/browser.md) for extension installation, pairing, tab selection, and snapshot pagination.

**Commands:** `tabs`, `select_tab`, `open`, `snapshot`, `click`, `dblclick`, `hover`, `fill`, `type`, `scroll`, `back`, `forward`, `reload`, `refresh`, `press`, `click_coords`

### `speak`

Text-to-speech output. Converts text to audio and plays it.

### `skill_execute`

Execute user-defined skills. See [Skills](../../03-features/skills.md).

### `tool_search`

Meta-tool always available to the agent. Lets it discover and activate additional tools mid-conversation without restarting the session.

**Parameters:**
- `query` (optional): Exact tool key to activate — either the class name (e.g. `"WebSearchTool"`) or the pydantic-ai runtime name (e.g. `"web_search"`). Omit to list tool status.

**List mode** (no query): Returns three sections:
- `ENABLED (user-selected)` — tools the user turned on in ConfigView
- `ACTIVE (AI-activated this session)` — tools the agent has already activated
- `AVAILABLE TO ACTIVATE` — deferrable tools not yet active

**Activation mode** (with query): Activates the matched tool immediately; the tool becomes callable in the agent's next step. Emits a `tool_activated` SSE event so the frontend can update ConfigView in real time.

Tools with `deferrable = False` (MemorySearchTool, SkillTool, SocialMessageTool) are excluded from the catalog and cannot be activated this way — they are always-on internals.

## Configuring Tools

### Default Tools

The default selection is `default_tools` in `src/suzent/config/model.py`.

### Custom Tool Selection

Specify tools in the agent configuration:

```python
config = {
    "model": "gemini/gemini-2.5-pro",
    "tools": [
        "WebSearchTool",
        "PlanningTool",
        "ReadFileTool",
        "RunCommandTool",
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
- If the tool is dangerous (writes, executes, sends), add HITL approval — see [Human-in-the-Loop](../../03-features/tools/human-in-the-loop.md)
- Return informative error messages as strings (don't raise exceptions)
- Set `deferrable = False` on the tool class if it should never appear in the `tool_search` catalog (e.g. always-on internals like MemorySearchTool)

## Tool Registry

The tool registry (`src/suzent/tools/registry.py`) provides programmatic access:

```python
from suzent.tools.registry import get_tool_function, list_available_tools

# Get a specific tool function
fn = get_tool_function("WebSearchTool")

# List all available tool names
names = list_available_tools()
```

## Permission engine

User-facing behavior is described in [Permissions & approvals](../../03-features/tools/human-in-the-loop.md). The rest of this section covers the API and event contract.

### APIs

```text
GET    /permissions?chat_id={chat_id}
POST   /permissions/rules
DELETE /permissions/rules/{rule_id}?destination=session|global&chat_id={chat_id}
GET    /chats/{chat_id}/permission-state
GET    /chats/{chat_id}/permission-mode
PUT    /chats/{chat_id}/permission-mode
```

Resume a suspended call through `/chat` or `/chat/send`:

```json
{
  "chat_id": "chat-id",
  "message": "",
  "resume_approvals": [
    {
      "request_id": "tool-call-id",
      "tool_call_id": "tool-call-id",
      "action_id": "allow_session",
      "feedback": "Optional user guidance"
    }
  ]
}
```

Legacy binary approval payloads remain accepted as allow-once or deny-only decisions. They cannot create remembered policies.

### Streaming Contract

Permission provenance is streamed separately from the tool result so the UI can
show how a deferred action was authorized. Full Access is labeled as allowed
without review; it must not be presented as an Auto classifier approval.

```json
{
  "name": "tool_permission_decision",
  "value": {
    "toolCallId": "tool-call-id",
    "behavior": "ask",
    "source": "auto_classifier",
    "reason": "This command changes workspace files.",
    "reasonCode": "auto_classifier_ask",
    "risk": "medium",
    "confidence": "high",
    "riskCategories": ["filesystem"],
    "reviewerModel": "openai/gpt-4.1-mini"
  }
}
```

The `tool_approval_request` custom event contains:

```json
{
  "approvalId": "tool-call-id",
  "toolCallId": "tool-call-id",
  "toolName": "run_command",
  "args": {"content": "npm test"},
  "decision": {
    "behavior": "ask",
    "reason": "Git commands require approval",
    "reasonCode": "shell_policy_ask",
    "risk": "high",
    "actions": []
  }
}
```

The frontend renders `decision.actions` in order, including feedback inputs and rule explanations declared by the backend. Pending contracts are persisted in `_pending_approvals` so the same prompt can be restored after refresh.

After a user acts on an approval prompt, Suzent streams
`tool_permission_resolution` with the selected action and scope. Older clients
can ignore provenance events and still rely on `tool_approval_request`.

### Audit Trail

Permission evaluations and user resolutions are appended to `permission-audit.jsonl` in the user configuration directory. Entries include chat, run, tool-call, mode, decision, reason, user action, and classifier or matched-rule metadata.

Arguments are bounded and recursively sanitized. Sensitive keys and common inline credential forms are redacted. The append is offloaded to a worker thread so audit logging never blocks the streaming event loop.

### Adding Approval to a Tool

Set `requires_approval = True` on the tool class:

```python
class MyTool(BaseTool):
    tool_name = "my_tool"
    requires_approval = True
```

The registry wraps it as a pydantic-ai deferred tool. Add deterministic read-only or mode-specific behavior to `PermissionEngine` when needed; otherwise the default decision asks before execution.

Keep execution-time validation inside the tool. Permission approval answers whether an operation may proceed, while the tool must still validate paths, symlinks, arguments, and current external state immediately before execution.

### Headless Runs

Cron, heartbeat, goals, dream jobs, and subagents use Auto mode with a non-interactive profile. They do not use blanket `auto_approve_tools` behavior. A headless action that cannot be classified safely is denied.

## Browser extension development

Browser-side source lives in `extensions/browser/`. The current installer clones
the repository, so no separate extension packaging or build step is required.
The optional download endpoint creates a ZIP from that directory. A standalone
Python wheel alone does not include the extension source. Python browser code lives
in `src/suzent/tools/browser/`, with the extension bridge in its `extension/` package.
No Node runtime is required for users. Load the source directory unpacked for development,
then reload the extension after changes. English and Chinese extension strings are
in `_locales/`. Run `uv run pytest tests/tools/test_browser_extension.py` for the
real bundled-Chromium extension regression, using an isolated test profile.

