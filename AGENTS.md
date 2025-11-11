# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Suzent is a full-stack AI agent chat application with persistent conversations, task planning, web search, and a newly implemented memory system. The architecture uses Python (Starlette + smolagents) for the backend and React (TypeScript + Vite) for the frontend.

## Development Setup

### Backend (Python)
```bash
# Activate environment
.venv/Scripts/activate  # Windows

# Install dependencies
uv sync                 # Base dependencies
uv sync --extra memory  # Include PostgreSQL memory system

# Install browser for WebpageTool
playwright install

# Start server (runs on port 8000)
python src/suzent/server.py
```

### Frontend (React)
```bash
cd frontend
npm install      # First time only
npm run dev      # Runs on port 5173, proxies /api/* to :8000
```

### Environment Variables (.env)
Required at project root:
```bash
# AI Model API Keys (at least one required)
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=xxx
GEMINI_API_KEY=xxx

# Optional: Privacy-focused web search
SEARXNG_BASE_URL=http://localhost:8080

# Optional: Memory system (PostgreSQL)
POSTGRES_HOST=localhost
POSTGRES_USER=suzent
POSTGRES_PASSWORD=your_password
POSTGRES_DB=suzent

# Optional: Logging
LOG_LEVEL=INFO
LOG_FILE=suzent.log
```

## Architecture

### Backend Structure (src/suzent/)
- **server.py** - Starlette ASGI app entry point with CORS
- **agent_manager.py** - Agent lifecycle: create, serialize/deserialize, tool injection, state management
- **streaming.py** - Server-Sent Events (SSE) streaming with background threads, cooperative cancellation
- **database.py** - SQLite operations for chats, plans, tasks
- **plan.py** - Plan/Task dataclasses, database I/O, markdown formatting
- **config.py** - YAML configuration with environment variable overrides, dynamic tool discovery
- **routes/** - Modular route handlers (chat, plan, config, mcp)
- **tools/** - Custom smolagents tools (WebSearchTool, PlanningTool, WebpageTool, FileTool)
- **memory/** - NEW: PostgreSQL + pgvector memory system (MemoryManager, MemorySearchTool, MemoryBlockUpdateTool)

### Frontend Structure (frontend/src/)
- **lib/api.ts** - REST API client for CRUD operations
- **lib/streaming.ts** - SSE client for agent responses
- **hooks/useChatStore.tsx** - React Context for chat state (messages, config, auto-save)
- **hooks/usePlan.tsx** - React Context for plan state and task monitoring
- **components/ChatWindow.tsx** - Message rendering with markdown, code blocks, streaming support
- **components/Sidebar.tsx** - Chat list, plan view, configuration tabs

### Key Patterns

#### Agent State Persistence
- Agent state (memory, tools, step count) pickled to `agent_state` BLOB in `chats` table
- `serialize_agent()` extracts serializable state before storage
- `deserialize_agent()` recreates agent with same config and memory on next request
- State saved after each streaming response completes (chat_routes.py:95)

#### Tool Context Injection
- Tools receive `chat_id` via `inject_chat_context()` before agent execution
- `PlanningTool` uses `_current_chat_id` attribute to associate plans with chats
- Prevents tools from requiring chat_id as LLM-exposed parameter
- Pattern: Tool has `set_chat_context(chat_id)` method called before `forward()`

#### Streaming Architecture
- **Hybrid threading model**: Agent runs in background thread, results enqueued to asyncio.Queue
- **Event types**: `action`, `planning`, `final_answer`, `stream_delta`, `plan_refresh`, `error`, `stopped`
- **Cancellation**: `StreamControl` holds both asyncio.Event and threading.Event for cooperative stop
- **Plan watching**: Background task polls database every 0.7s for plan changes during streaming

#### Memory System (NEW - feat/memory branch)
- **PostgreSQL + pgvector** for hybrid storage (relational + vector embeddings)
- **Core Memory**: 4 blocks (persona, user, facts, context) always visible in agent context
- **Archival Memory**: Unlimited semantic storage with hybrid search (vector + full-text + importance + recency)
- **Automatic Extraction**: Facts automatically extracted from conversations with deduplication
- **Agent Tools**: Only 2 tools exposed - `memory_search` (recall) and `memory_block_update` (update core blocks)
- **Async Operations**: Connection pooling with asyncpg for concurrent safety

## Common Development Tasks

### Running Tests
Currently no automated test suite. Manual testing workflow:
1. Start backend and frontend servers
2. Create new chat, send message
3. Verify streaming, plan updates, chat persistence
4. Test stop stream, chat deletion, chat switching

### Adding a New Tool
1. Create `src/suzent/tools/yourtool_tool.py` inheriting from `smolagents.tools.Tool`
2. Define `name`, `description`, `inputs` (JSON schema), `output_type`
3. Implement `forward()` method with business logic
4. If tool needs chat_id context, add:
   ```python
   skip_forward_signature_validation = True

   def __init__(self):
       self._current_chat_id = None

   def set_chat_context(self, chat_id: str):
       self._current_chat_id = chat_id
   ```
5. Register in `agent_manager.py` `tool_module_map` for loading
6. Tool will be auto-discovered via `Config.get_tool_options()` if class name matches pattern

### Working with Plans
- **Creation**: PlanningTool creates plan + tasks in database
- **Versioning**: Each `write_plan_to_database()` creates new record by default (preserves history)
- **In-place update**: Use `preserve_history=False` for atomic updates
- **Status lifecycle**: `pending` → `in_progress` → `completed` | `failed`
- **Frontend sync**: Plan updates trigger `plan_refresh` SSE events

### Configuration (config/default.yaml)
- **default.example.yaml** - Template with defaults
- **default.yaml** - User overrides (gitignored)
- Environment variables override file settings
- Access via `GET /config` endpoint
- Supports: model selection, agent type, MCP server URLs, custom instructions, tool selection

### Database Schema
**SQLite (chats.db)**:
- `chats` - id, title, timestamps, config (JSON), messages (JSON), agent_state (BLOB)
- `plans` - id, chat_id (FK), objective, timestamps
- `tasks` - id, plan_id (FK), number, description, status, note, timestamps

**PostgreSQL (memory system - optional)**:
- `memory_blocks` - Core memory (persona, user, facts, context)
- `archival_memories` - Unlimited storage with vector embeddings, full-text search
- `memory_relationships` - Links between related memories
- Requires `vector` and `pg_trgm` extensions

## Important Gotchas

1. **Agent serialization fails**: Ensure tools don't hold non-serializable objects (open files, sockets)
2. **Plan not updating**: Check `chat_id` context is injected before agent runs
3. **Stream hanging**: Verify `stream_controls[chat_id]` cleaned up on stream end
4. **Tool not found**: Check `tool_module_map` in agent_manager.py matches class name in tools/ directory
5. **Code indentation in frontend**: Python rendering uses `normalizePythonCode()` - don't strip whitespace in backend
6. **Memory system**: Requires PostgreSQL + pgvector extension, separate from SQLite chat storage

## Technology Stack

**Backend**: Starlette, smolagents, LiteLLM (multi-provider), SQLite, uvicorn, crawl4ai, asyncpg, pgvector
**Frontend**: React 18, TypeScript, Vite, Tailwind CSS, react-markdown, marked
**Package Manager**: uv (Python - fast, Cargo-based), npm (Node.js)

## API Endpoints

- `POST /chat` - Stream agent response (SSE)
- `POST /chat/stop` - Stop active stream
- `GET /chats` - List all chats
- `POST /chats` - Create new chat
- `GET /chats/{id}` - Get specific chat with messages
- `PUT /chats/{id}` - Update chat (title, config)
- `DELETE /chats/{id}` - Delete chat (cascades to plans/tasks)
- `GET /plan?chat_id={id}` - Get current plan
- `GET /plans?chat_id={id}` - Get plan history
- `GET /config` - Get configuration options
- `POST /config` - Update configuration
- `GET /mcp_servers` - List MCP servers
- `POST /mcp_servers` - Add MCP server

## Design Philosophy

- **Modularity**: Self-contained tools, configuration-driven behavior
- **Async-First**: Starlette/ASGI for concurrency, SSE for real-time updates
- **Durable State**: Agent serialization without session management
- **React Context**: Avoids prop drilling, separates concerns (chat vs plan)
- **Extensibility**: Easy tool/model addition via configuration
- **Memory-Aware**: Optional long-term memory with automatic fact extraction

## Recent Changes (feat/memory branch)

The memory system is a recent addition implementing Letta-style memory:
- PostgreSQL + pgvector replaces ChromaDB approach
- Automatic fact extraction from conversations
- Hybrid search combining semantic similarity, full-text, importance, and recency
- Simplified agent interface (only 2 tools vs. 5 in Letta)
- See `docs/MEMORY_SYSTEM_DESIGN.md` for full specifications
- See `MEMORY_POC_SUMMARY.md` for implementation summary
