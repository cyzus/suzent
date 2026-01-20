"""
Unit tests for SQLModel database layer.
"""

import os
import tempfile

import pytest

from suzent.database import (
    ChatDatabase,
    ChatSummaryModel,
    PlanModel,
    UserPreferencesModel,
)


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database = ChatDatabase(db_path)
    yield database

    # Dispose engine to release file locks (Windows)
    database.engine.dispose()

    # Cleanup
    try:
        os.unlink(db_path)
    except PermissionError:
        pass  # Windows may still hold locks briefly


class TestChatOperations:
    """Tests for chat CRUD operations."""

    def test_create_chat(self, db):
        chat_id = db.create_chat("Test Chat", {"model": "gpt-4"})
        assert chat_id is not None
        assert len(chat_id) == 36  # UUID format

    def test_get_chat(self, db):
        chat_id = db.create_chat(
            "Test Chat",
            {"model": "gpt-4"},
            [{"role": "user", "content": "Hello"}],
        )

        chat = db.get_chat(chat_id)
        assert chat is not None
        assert chat.title == "Test Chat"
        assert chat.config["model"] == "gpt-4"
        assert len(chat.messages) == 1
        assert chat.messages[0]["content"] == "Hello"

    def test_update_chat(self, db):
        chat_id = db.create_chat("Original Title", {})

        result = db.update_chat(chat_id, title="Updated Title")
        assert result is True

        chat = db.get_chat(chat_id)
        assert chat.title == "Updated Title"

    def test_delete_chat(self, db):
        chat_id = db.create_chat("To Delete", {})
        assert db.get_chat(chat_id) is not None

        result = db.delete_chat(chat_id)
        assert result is True
        assert db.get_chat(chat_id) is None

    def test_list_chats(self, db):
        db.create_chat("Chat 1", {})
        db.create_chat("Chat 2", {})
        db.create_chat("Chat 3", {})

        chats = db.list_chats()
        assert len(chats) == 3
        # ChatSummaryModel uses camelCase for frontend compat
        assert isinstance(chats[0], ChatSummaryModel)

    def test_get_chat_count(self, db):
        db.create_chat("Chat 1", {})
        db.create_chat("Chat 2", {})

        count = db.get_chat_count()
        assert count == 2


class TestPlanOperations:
    """Tests for plan and task CRUD operations."""

    def test_create_plan(self, db):
        chat_id = db.create_chat("Test Chat", {})

        plan_id = db.create_plan(
            chat_id,
            "Test Objective",
            [{"number": 1, "description": "Step 1", "status": "pending"}],
        )
        assert plan_id is not None

    def test_get_plan(self, db):
        chat_id = db.create_chat("Test Chat", {})
        db.create_plan(
            chat_id,
            "My Objective",
            [
                {"number": 1, "description": "First step"},
                {"number": 2, "description": "Second step"},
            ],
        )

        plan = db.get_plan(chat_id)
        assert plan is not None
        assert isinstance(plan, PlanModel)
        assert plan.objective == "My Objective"
        assert len(plan.tasks) == 2
        assert plan.tasks[0].description == "First step"

    def test_update_task_status(self, db):
        chat_id = db.create_chat("Test Chat", {})
        db.create_plan(
            chat_id,
            "Objective",
            [{"number": 1, "description": "Step 1", "status": "pending"}],
        )

        result = db.update_task_status(chat_id, 1, "completed", note="Done!")
        assert result is True

        plan = db.get_plan(chat_id)
        assert plan.tasks[0].status == "completed"
        assert plan.tasks[0].note == "Done!"

    def test_delete_plan(self, db):
        chat_id = db.create_chat("Test Chat", {})
        db.create_plan(chat_id, "Objective", [])

        assert db.get_plan(chat_id) is not None

        result = db.delete_plan(chat_id)
        assert result is True
        assert db.get_plan(chat_id) is None


class TestUserPreferences:
    """Tests for user preferences singleton."""

    def test_save_and_get_preferences(self, db):
        db.save_user_preferences(model="gpt-4", memory_enabled=True)

        prefs = db.get_user_preferences()
        assert prefs is not None
        assert isinstance(prefs, UserPreferencesModel)
        assert prefs.model == "gpt-4"
        assert prefs.memory_enabled is True

    def test_update_preferences(self, db):
        db.save_user_preferences(model="gpt-4")
        db.save_user_preferences(model="claude-3")

        prefs = db.get_user_preferences()
        assert prefs.model == "claude-3"


class TestMCPServers:
    """Tests for MCP server management."""

    def test_add_url_server(self, db):
        result = db.add_mcp_server(
            "test-server", config={"type": "url", "url": "http://localhost:8080"}
        )
        assert result is True

        servers = db.get_mcp_servers()
        # Find the server in list
        server = next((s for s in servers if s.name == "test-server"), None)
        assert server is not None
        assert server.type == "url"
        assert server.url == "http://localhost:8080"

    def test_add_stdio_server(self, db):
        result = db.add_mcp_server(
            "stdio-server",
            config={"type": "stdio", "command": "node", "args": ["server.js"]},
        )
        assert result is True

        servers = db.get_mcp_servers()
        server = next((s for s in servers if s.name == "stdio-server"), None)
        assert server is not None
        assert server.type == "stdio"
        assert server.command == "node"

    def test_remove_server(self, db):
        db.add_mcp_server(
            "to-remove", config={"type": "url", "url": "http://remove.me"}
        )
        assert db.remove_mcp_server("to-remove") is True

        servers = db.get_mcp_servers()
        server = next((s for s in servers if s.name == "to-remove"), None)
        assert server is None

    def test_toggle_server_enabled(self, db):
        db.add_mcp_server(
            "toggle-test", config={"type": "url", "url": "http://test.com"}
        )

        db.set_mcp_server_enabled("toggle-test", False)
        servers = db.get_mcp_servers()
        server = next(s for s in servers if s.name == "toggle-test")
        assert server.enabled is False

        db.set_mcp_server_enabled("toggle-test", True)
        servers = db.get_mcp_servers()
        server = next(s for s in servers if s.name == "toggle-test")
        assert server.enabled is True
