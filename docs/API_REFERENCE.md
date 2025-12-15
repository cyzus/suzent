# Suzent API Reference

Complete API documentation for Suzent backend endpoints.

**Base URL**: `http://localhost:8000` (development)

## Authentication

Currently no authentication required. Recommended for production:
- Add API key authentication
- Use reverse proxy with auth
- Implement rate limiting

## Response Format

All responses are JSON unless specified otherwise.

**Success Response**:
```json
{
  "data": { ... },
  "status": "success"
}
```

**Error Response**:
```json
{
  "error": "Error message",
  "details": { ... }
}
```

---

## Chat Endpoints

### Stream Chat Response
```http
POST /chat
Content-Type: application/json
```

**Request Body**:
```json
{
  "message": "Your message",
  "chat_id": "optional-existing-chat-id",
  "config": {
    "model": "openai/gpt-4",
    "agent": "ToolCallingAgent",
    "tools": ["WebSearchTool", "PlanningTool"]
  }
}
```

**Response**: Server-Sent Events (SSE) stream

**Event Types**:
- `action` - Agent tool execution
- `planning` - Plan creation/update
- `final_answer` - Final response
- `stream_delta` - Streaming text
- `plan_refresh` - Plan updated
- `error` - Error occurred
- `stopped` - Stream stopped

### Stop Chat Stream
```http
POST /chat/stop
Content-Type: application/json
```

**Request Body**:
```json
{
  "chat_id": "chat-id-to-stop"
}
```

### List Chats
```http
GET /chats?limit=50&offset=0&search=query
```

**Response**:
```json
[
  {
    "id": "chat-123",
    "title": "Chat Title",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T01:00:00",
    "message_count": 10
  }
]
```

### Get Chat
```http
GET /chats/{chat_id}
```

**Response**:
```json
{
  "id": "chat-123",
  "title": "Chat Title",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T01:00:00",
  "config": { ... },
  "messages": [ ... ]
}
```

### Create Chat
```http
POST /chats
Content-Type: application/json
```

**Request Body**:
```json
{
  "title": "New Chat",
  "config": {
    "model": "openai/gpt-4",
    "agent": "ToolCallingAgent",
    "tools": ["WebSearchTool"]
  },
  "messages": []
}
```

### Update Chat
```http
PUT /chats/{chat_id}
Content-Type: application/json
```

**Request Body**: Same as create

### Delete Chat
```http
DELETE /chats/{chat_id}
```

---

## Plan Endpoints

### Get Current Plan
```http
GET /plan?chat_id={chat_id}
```

**Response**:
```json
{
  "id": 1,
  "chat_id": "chat-123",
  "objective": "Complete the task",
  "tasks": [
    {
      "number": 1,
      "description": "First task",
      "status": "completed",
      "note": "Done successfully"
    }
  ],
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T01:00:00"
}
```

### Get Plan History
```http
GET /plans?chat_id={chat_id}&limit=10
```

Returns array of plans ordered by creation date.

---

## Configuration Endpoints

### Get Configuration
```http
GET /config
```

**Response**:
```json
{
  "model_options": ["openai/gpt-4", "anthropic/claude-3"],
  "agent_options": ["ToolCallingAgent", "CodeAgent"],
  "tool_options": ["WebSearchTool", "PlanningTool"],
  "mcp_urls": { ... },
  "default_config": { ... }
}
```

### Save Preferences
```http
POST /preferences
Content-Type: application/json
```

**Request Body**:
```json
{
  "model": "openai/gpt-4",
  "agent": "ToolCallingAgent",
  "tools": ["WebSearchTool"],
  "memory_enabled": false
}
```

---

## MCP Server Endpoints

### List MCP Servers
```http
GET /mcp_servers
```

### Add MCP Server
```http
POST /mcp_servers
Content-Type: application/json
```

**Request Body**:
```json
{
  "name": "Server Name",
  "url": "https://server.com/mcp"
}
```

### Remove MCP Server
```http
POST /mcp_servers/remove
Content-Type: application/json
```

**Request Body**:
```json
{
  "server_id": 1
}
```

### Set MCP Server Enabled
```http
POST /mcp_servers/enabled
Content-Type: application/json
```

**Request Body**:
```json
{
  "server_id": 1,
  "enabled": true
}
```

---

## Memory Endpoints

*(Optional - requires PostgreSQL + pgvector)*

### Get Core Memory
```http
GET /memory/core?user_id={user_id}
```

**Response**:
```json
{
  "persona": { "id": 1, "label": "persona", "value": "..." },
  "user": { "id": 2, "label": "user", "value": "..." },
  "facts": { "id": 3, "label": "facts", "value": "..." },
  "context": { "id": 4, "label": "context", "value": "..." }
}
```

### Update Core Memory Block
```http
PUT /memory/core
Content-Type: application/json
```

**Request Body**:
```json
{
  "user_id": "default-user",
  "block_name": "user",
  "value": "Updated content"
}
```

### Search Archival Memory
```http
GET /memory/archival?query=search&limit=10&user_id={user_id}
```

### Delete Archival Memory
```http
DELETE /memory/archival/{memory_id}?user_id={user_id}
```

### Get Memory Stats
```http
GET /memory/stats?user_id={user_id}
```

---

## Export/Import Endpoints

### Export Chat
```http
GET /export/chat?chat_id={chat_id}&format={json|markdown}
```

**Response**: File download (JSON or Markdown)

### Export All Chats
```http
GET /export/all
```

**Response**: ZIP file with all chats

### Import Chat
```http
POST /import/chat?preserve_id={true|false}
Content-Type: application/json
```

**Request Body**: Chat JSON from export

### Create Backup
```http
GET /backup
```

**Response**: SQLite database file

### Get Database Stats
```http
GET /stats
```

**Response**:
```json
{
  "total_chats": 42,
  "total_messages": 500,
  "total_plans": 15,
  "total_tasks": 67,
  "database_size_bytes": 1048576,
  "database_size_mb": 1.0,
  "oldest_chat": "2024-01-01T00:00:00",
  "newest_chat": "2024-01-15T12:00:00"
}
```

---

## Health & Monitoring Endpoints

### Health Check
```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T12:00:00",
  "uptime_seconds": 3600
}
```

### Readiness Check
```http
GET /ready
```

**Response** (200 if ready, 503 if not):
```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "memory_system": "ok"
  },
  "timestamp": "2024-01-15T12:00:00"
}
```

### System Info
```http
GET /info
```

**Response**:
```json
{
  "version": "0.1.0",
  "python_version": "3.12.0",
  "platform": "linux",
  "uptime_seconds": 3600,
  "database": { ... },
  "config": { ... }
}
```

### Metrics
```http
GET /metrics
```

**Response**: Prometheus-format metrics

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Resource doesn't exist |
| 500 | Internal Server Error |
| 503 | Service Unavailable - System not ready |

---

## Rate Limiting

Not currently implemented. Recommended for production:
```
Rate Limit: 100 requests/minute per IP
Burst: 20 requests
```

---

## WebSocket Support

Not currently supported. SSE used for streaming.

---

## Examples

### Python Client
```python
import requests

# Create chat
response = requests.post(
    "http://localhost:8000/chats",
    json={
        "title": "My Chat",
        "config": {"model": "openai/gpt-4"},
        "messages": []
    }
)
chat_id = response.json()["id"]

# Stream message
import sseclient

response = requests.post(
    "http://localhost:8000/chat",
    json={"message": "Hello", "chat_id": chat_id},
    stream=True
)

client = sseclient.SSEClient(response)
for event in client.events():
    print(event.data)
```

### JavaScript Client
```javascript
// Create chat
const response = await fetch('http://localhost:8000/chats', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: 'My Chat',
    config: { model: 'openai/gpt-4' },
    messages: []
  })
});
const { id: chatId } = await response.json();

// Stream message
const eventSource = new EventSource(
  'http://localhost:8000/chat',
  {
    method: 'POST',
    body: JSON.stringify({
      message: 'Hello',
      chat_id: chatId
    })
  }
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

---

## Version History

- **0.1.0** (2024-12-15): Initial API release
  - Chat management
  - Planning system
  - Memory system (optional)
  - Export/Import
  - Health checks

---

For more information, see:
- [README.md](../README.md)
- [AGENTS.md](../AGENTS.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
