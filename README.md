# Suzent

An AI agent chat application with persistent conversation management.

## Features

- **Persistent Chat Storage**: All conversations are automatically saved to a SQLite database
- **Multi-Chat Management**: Create, switch between, and manage multiple chat sessions
- **Auto-Save**: Messages are automatically saved as you chat
- **Chat History**: Browse and continue previous conversations
- **Real-time Planning**: AI agent can create and manage task plans
- **Model Configuration**: Support for multiple AI models and agents

## Quick Start

1. **Activate virtual environment:**
```bash
.venv/Scripts/activate
```

2. **Install dependencies:**
```bash
pip install -e .
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

## Chat Persistence

The application now includes full chat persistence:

- **Database**: SQLite database (`chats.db`) stores all conversations
- **Auto-save**: Messages are saved automatically as you chat
- **Chat List**: View all your conversations in the sidebar "Chats" tab
- **Continue Conversations**: Click any chat in the list to resume
- **New Chats**: Click "New Chat" to start a fresh conversation
- **Delete Chats**: Hover over a chat and click the trash icon to delete

## API Endpoints

The backend provides these chat management endpoints:

- `GET /chats` - List all chats
- `POST /chats` - Create a new chat
- `GET /chats/{id}` - Get a specific chat
- `PUT /chats/{id}` - Update a chat
- `DELETE /chats/{id}` - Delete a chat

