"""Unit tests for SQLModel database layer."""

import os
import sqlite3

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect

from suzent.database import (
    ChatDatabase,
    ChatSummaryModel,
    PlanModel,
    UserPreferencesModel,
)


@pytest.fixture
def db(temp_db):
    """Use shared database fixture."""
    return temp_db


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

    def test_snapshot_revision_and_guarded_finalize(self, db):
        chat_id = db.create_chat("Revision Chat", {})

        rev1 = db.commit_snapshot_state(chat_id, b"state-1")
        assert rev1 == 1

        chat = db.get_chat(chat_id)
        assert chat is not None
        assert chat.state_revision == 1
        assert chat.state_stage == "snapshot"

        ok = db.finalize_state_if_revision_matches(
            chat_id=chat_id,
            expected_revision=1,
            agent_state=b"state-final-1",
            messages=[{"role": "assistant", "content": "done"}],
        )
        assert ok is True

        chat = db.get_chat(chat_id)
        assert chat is not None
        assert chat.finalized_revision == 1
        assert chat.state_stage == "finalized"
        assert chat.messages[-1]["content"] == "done"

        rev2 = db.commit_snapshot_state(chat_id, b"state-2")
        assert rev2 == 2

        stale = db.finalize_state_if_revision_matches(
            chat_id=chat_id,
            expected_revision=1,
            agent_state=b"state-stale",
            messages=[{"role": "assistant", "content": "stale"}],
        )
        assert stale is False

        chat = db.get_chat(chat_id)
        assert chat is not None
        assert chat.state_revision == 2
        assert chat.finalized_revision == 1
        assert chat.agent_state == b"state-2"


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

    def test_save_embedding_and_extraction_models(self, db):
        """Test that embedding and extraction models can be saved and retrieved."""
        db.save_memory_config(
            embedding_model="gemini/gemini-embedding-001",
            extraction_model="gemini/gemini-2.5-flash",
        )

        config = db.get_memory_config()
        assert config is not None
        assert config.embedding_model == "gemini/gemini-embedding-001"
        assert config.extraction_model == "gemini/gemini-2.5-flash"

    def test_static_preferences_are_not_sqlite_tables(self, db):
        db.save_user_preferences(model="gpt-4", memory_enabled=True)
        db.save_memory_config(embedding_model="embed", extraction_model="extract")
        db.save_api_key("_PROVIDER_CONFIG_", '{"openai": {}}')

        tables = set(inspect(db.engine).get_table_names())

        assert "user_preferences" not in tables
        assert "memory_config" not in tables
        assert "api_keys" not in tables
        assert db.get_api_key("_PROVIDER_CONFIG_") == '{"openai": {}}'

    def test_legacy_static_tables_are_migrated_out_of_sqlite(
        self, tmp_path, monkeypatch
    ):
        db_path = tmp_path / "legacy.db"
        config_path = tmp_path / "config.yaml"
        monkeypatch.setenv("SUZENT_USER_CONFIG_PATH", str(config_path))
        monkeypatch.setenv("SUZENT_SECRET_DB_PATH", str(tmp_path / "secrets.db"))
        monkeypatch.setenv("SUZENT_SECRET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("SUZENT_SECRET_BACKEND", "encrypted_sqlite")

        from suzent.core import secrets

        secrets._instance = None

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE user_preferences (
                    id INTEGER PRIMARY KEY,
                    model TEXT,
                    agent TEXT,
                    tools JSON,
                    memory_enabled BOOLEAN,
                    sandbox_enabled BOOLEAN,
                    sandbox_volumes JSON,
                    updated_at DATETIME
                )
                """
            )
            conn.execute(
                """
                INSERT INTO user_preferences
                VALUES (1, 'gpt-4', 'Agent', '["ReadFileTool"]', 1, 0,
                        '["C:/work:/mnt/work"]', '2026-01-01T00:00:00')
                """
            )
            conn.execute(
                """
                CREATE TABLE memory_config (
                    id INTEGER PRIMARY KEY,
                    embedding_model TEXT,
                    extraction_model TEXT,
                    updated_at DATETIME
                )
                """
            )
            conn.execute(
                """
                INSERT INTO memory_config
                VALUES (1, 'embed-model', 'extract-model', '2026-01-01T00:00:00')
                """
            )
            conn.execute(
                """
                CREATE TABLE api_keys (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME
                )
                """
            )
            conn.execute(
                """
                INSERT INTO api_keys VALUES
                ('OPENAI_API_KEY', 'sk-test', '2026-01-01T00:00:00'),
                ('_PROVIDER_CONFIG_', '{"openai":{"enabled_models":["openai/gpt-4"]}}',
                 '2026-01-01T00:00:00')
                """
            )

        db = ChatDatabase(str(db_path))

        tables = set(inspect(db.engine).get_table_names())
        prefs = db.get_user_preferences()
        memory = db.get_memory_config()

        assert "user_preferences" not in tables
        assert "memory_config" not in tables
        assert "api_keys" not in tables
        assert prefs is not None
        assert prefs.model == "gpt-4"
        assert prefs.tools == ["ReadFileTool"]
        assert prefs.memory_enabled is True
        assert prefs.sandbox_enabled is False
        assert prefs.sandbox_volumes == ["C:/work:/mnt/work"]
        assert memory is not None
        assert memory.embedding_model == "embed-model"
        assert db.get_api_key("_PROVIDER_CONFIG_") == (
            '{"openai":{"enabled_models":["openai/gpt-4"]}}'
        )
        assert secrets.get_secret_manager().get("OPENAI_API_KEY") == "sk-test"

        db.engine.dispose()

    def test_legacy_secret_migrates_even_when_env_var_is_set(
        self, tmp_path, monkeypatch
    ):
        db_path = tmp_path / "legacy-env.db"
        monkeypatch.setenv("SUZENT_USER_CONFIG_PATH", str(tmp_path / "config.yaml"))
        secret_db_path = tmp_path / "secrets.db"
        monkeypatch.setenv("SUZENT_SECRET_DB_PATH", str(secret_db_path))
        monkeypatch.setenv("SUZENT_SECRET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("SUZENT_SECRET_BACKEND", "encrypted_sqlite")
        monkeypatch.setenv("OPENAI_API_KEY", "temporary-env-key")

        from suzent.core import secrets

        secrets._instance = None

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE api_keys (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME
                )
                """
            )
            conn.execute(
                """
                INSERT INTO api_keys
                VALUES ('OPENAI_API_KEY', 'persisted-db-key', '2026-01-01T00:00:00')
                """
            )

        db = ChatDatabase(str(db_path))
        secret_manager = secrets.get_secret_manager()

        assert "api_keys" not in set(inspect(db.engine).get_table_names())
        assert secret_manager.has_backend_value("OPENAI_API_KEY") is True
        assert secret_manager.get("OPENAI_API_KEY") == "persisted-db-key"
        assert b"persisted-db-key" not in secret_db_path.read_bytes()
        assert os.environ["OPENAI_API_KEY"] == "temporary-env-key"

        db.engine.dispose()


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
