# Suzent

An AI agent chat application with persistent conversation management, web search capabilities, and task planning.

## Features

- **Persistent Chat Storage**: All conversations are automatically saved to a SQLite database
- **Multi-Chat Management**: Create, switch between, and manage multiple chat sessions
- **Auto-Save**: Messages are automatically saved as you chat
- **Chat History**: Browse and continue previous conversations
- **Real-time Planning**: AI agent can create and manage task plans
- **Model Configuration**: Support for multiple AI models and agents
- **Privacy-Focused Web Search**: Optional SearXNG integration for privacy-respecting search
- **Extensible Tools**: Easy to add custom tools and capabilities

## 📚 Documentation

For detailed documentation, please see the [docs](./docs) folder:


## Quick Start

Create or modify `.env`

```bash
OPENAI_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=xxx
GEMINI_API_KEY=xxx
ANTHROPIC_API_KEY=sk-xxx

# Optional: Use SearXNG for privacy-focused web search
# SEARXNG_BASE_URL=http://localhost:8080
```


1. **Activate virtual environment:**
```bash
.venv/Scripts/activate
```

2. **Install dependencies:**
```bash
uv sync
```

3. **Start the backend server:**
```bash
python src/suzent/server.py
```

4. **Start the frontend (in a new terminal):**
```bash
cd frontend
npm install  # First time only
npm run dev
```

5. **Open your browser to:** `http://localhost:5173`

## 🛠️ Tools

Suzent includes several powerful tools for the AI agent:

### WebSearchTool
- **Flexible Search**: Automatically uses SearXNG if configured, or falls back to default web search
- **Privacy-Focused**: SearXNG provides meta-search without tracking
- **Clean Output**: Results formatted in readable markdown
- **Advanced Parameters**: Supports categories, language filters, time ranges, and pagination (SearXNG only)

### PlanningTool
- **Structured Planning**: Create and manage task plans
- **Context-Aware**: Plans are associated with specific chats

### WebpageTool
- **Content Retrieval**: Fetch and process web page content

**For detailed tool documentation and SearXNG setup, see:**
- [Tools Guide](./docs/tools.md)
- [SearXNG Setup Guide](./docs/searxng-setup.md)

## 💾 Chat Persistence

The application now includes full chat persistence:

- **Database**: SQLite database (`chats.db`) stores all conversations
- **Auto-save**: Messages are saved automatically as you chat
- **Chat List**: View all your conversations in the sidebar "Chats" tab
- **Continue Conversations**: Click any chat in the list to resume
- **New Chats**: Click "New Chat" to start a fresh conversation
- **Delete Chats**: Hover over a chat and click the trash icon to delete

## 🔌 API Endpoints

The backend provides these chat management endpoints:

- `GET /chats` - List all chats
- `POST /chats` - Create a new chat
- `GET /chats/{id}` - Get a specific chat
- `PUT /chats/{id}` - Update a chat
- `DELETE /chats/{id}` - Delete a chat
- `GET /plan?chat_id={id}` - Get the plan for a specific chat

For complete API documentation, see [API Reference](./docs/api-reference.md) (coming soon).

## 📖 Additional Documentation

- **[Complete Documentation](./docs/README.md)** - Full documentation index
- **[Tools Documentation](./src/suzent/tools/README.md)** - Tools directory README
- **[Frontend Documentation](./frontend/README.md)** - Frontend-specific documentation

## 🤝 Contributing

Contributions are welcome! Please see the [Development Guide](./docs/development.md) for information on extending Suzent.

## 📄 License

See the [LICENSE](./LICENSE) file for details.

