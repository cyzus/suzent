# Suzent

An AI agent chat application with persistent conversations, task planning, web search, and optional long-term memory.

**Stack**: Python (Starlette + smolagents) backend, React (TypeScript + Vite) frontend

## Features

- **Persistent Chats** - Auto-saved conversations in SQLite
- **Task Planning** - Real-time task tracking and status management
- **Long-Term Memory** - Optional PostgreSQL + pgvector with semantic search
- **Multi-Model Support** - OpenAI, Anthropic, DeepSeek, Qwen, Gemini
- **Web Search** - Privacy-focused SearXNG integration or default search
- **Streaming Responses** - Real-time SSE updates
- **MCP Support** - Model Context Protocol server integration
- **Extensible** - Easy to add custom tools
- **Data Export/Import** - Export chats to JSON/Markdown, create backups
- **Health Monitoring** - Health checks, metrics, system info endpoints
- **Security** - Rate limiting, API authentication, input validation (optional)
- **Testing** - Comprehensive test suite with CI/CD
- **Developer Tools** - Setup scripts, linting, comprehensive documentation


## Quick Start

**Prerequisites**: Python 3.10+, Node.js 18+, PostgreSQL (optional)

### 1. Configure Environment

Create `.env` file with at least one API key:

```bash
# At least one AI API key required
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=xxx
GEMINI_API_KEY=xxx

# Optional: SearXNG for privacy-focused search
SEARXNG_BASE_URL=http://localhost:8080

# Optional: Memory system (requires PostgreSQL + pgvector)
POSTGRES_HOST=localhost
POSTGRES_USER=suzent
POSTGRES_PASSWORD=your_password
POSTGRES_DB=suzent
```

### 2. Install Dependencies

```bash
# Activate environment
.venv/Scripts/activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install
uv sync  # Base install
uv sync --extra memory  # With memory system
playwright install  # For WebpageTool
```

### 3. Run

```bash
# Backend (terminal 1)
python src/suzent/server.py  # Runs on :8000

# Frontend (terminal 2)
cd frontend
npm install  # First time only
npm run dev  # Runs on :5173
```

Open `http://localhost:5173`

## Tools

- **WebSearchTool** - SearXNG or default web search with markdown formatting
- **PlanningTool** - Task planning with status tracking (pending → in_progress → completed/failed)
- **WebpageTool** - Fetch and extract web page content
- **FileTool** - File read/write operations
- **Memory Tools** (optional) - Semantic search and core memory updates

See [docs/tools.md](./docs/tools.md) for details and [docs/searxng-setup.md](./docs/searxng-setup.md) for SearXNG setup.

## Storage

### SQLite (chats.db)
- Auto-saved conversations with agent state
- Plans and tasks tracking
- Browse, continue, or delete chats from sidebar

### PostgreSQL Memory (Optional)
Letta-style long-term memory with:
- **Core Memory**: 4 blocks (persona, user, facts, context) always in agent context
- **Archival Memory**: Unlimited semantic search with hybrid scoring
- **Auto Fact Extraction**: Automatic deduplication from conversations

## API Endpoints

### Core Endpoints
```
POST   /chat                Stream agent response (SSE)
POST   /chat/stop           Stop active stream
GET    /chats               List all chats
POST   /chats               Create new chat
GET    /chats/{id}          Get chat with messages
PUT    /chats/{id}          Update chat
DELETE /chats/{id}          Delete chat
GET    /plan                Get current plan
GET    /plans               Get plan history
GET    /config              Get configuration
POST   /preferences         Update configuration
```

### Export/Import Endpoints
```
GET    /export/chat         Export chat (JSON/Markdown)
GET    /export/all          Export all chats (ZIP)
POST   /import/chat         Import chat from JSON
GET    /backup              Create database backup
GET    /stats               Get database statistics
```

### Monitoring Endpoints
```
GET    /health              Health check
GET    /ready               Readiness check
GET    /info                System information
GET    /metrics             Prometheus metrics
```

See [docs/API_REFERENCE.md](./docs/API_REFERENCE.md) for complete API documentation.

## Architecture

**Backend**: Starlette ASGI + smolagents + LiteLLM
**Frontend**: React + TypeScript + Vite + Tailwind
**Database**: SQLite (chats), PostgreSQL + pgvector (memory)

```
src/suzent/
├── server.py         # ASGI app entry point
├── agent_manager.py  # Agent lifecycle & serialization
├── streaming.py      # SSE streaming
├── database.py       # SQLite operations
├── routes/           # API endpoints
├── tools/            # Custom tools
└── memory/           # Memory system

frontend/src/
├── lib/              # API & streaming clients
├── hooks/            # React Context stores
└── components/       # UI components
```

**Key Patterns**: Agent state persistence, tool context injection, hybrid threading for SSE, semantic memory search

## Documentation

- **[AGENTS.md](./AGENTS.md)** - Developer guide and architecture
- **[CONTRIBUTING.md](./CONTRIBUTING.md)** - How to contribute
- **[SECURITY.md](./SECURITY.md)** - Security policies and best practices
- **[docs/API_REFERENCE.md](./docs/API_REFERENCE.md)** - Complete API documentation
- **[docs/tools.md](./docs/tools.md)** - Tool documentation
- **[docs/searxng-setup.md](./docs/searxng-setup.md)** - SearXNG setup guide
- **[docs/MEMORY_SYSTEM_DESIGN.md](./docs/MEMORY_SYSTEM_DESIGN.md)** - Memory system specs

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

Quick start for contributors:
```bash
./scripts/setup_dev.sh  # Automated setup
# or follow manual setup in CONTRIBUTING.md
```

## Security

For security issues, please see [SECURITY.md](./SECURITY.md).

Optional security features:
- **Rate Limiting**: Limit requests per IP
- **API Authentication**: Protect endpoints with API keys
- **Input Validation**: Comprehensive validation to prevent attacks

## Testing

Run tests:
```bash
# Backend tests
uv run pytest test/ -v

# Frontend build
cd frontend && npm run build

# Code linting
uv run ruff check src/
```

CI/CD runs automatically on pull requests.

