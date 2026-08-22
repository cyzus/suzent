"""Unit tests for SQLModel database layer."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect

from suzent.database import (
    AgentInboxMessageModel,
    ChatDatabase,
    ChatSummaryModel,
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

    def test_clone_chat_to_point_copies_reusable_config_and_truncates_messages(
        self, db
    ):
        source_id = db.create_chat(
            "Original",
            {
                "model": "gpt-4",
                "tools": ["read_file"],
                "tool_approval_policy": {"bash_execute": "always_allow"},
                "permission_mode": "full_access",
                "platform": "subagent",
                "parent_chat_id": "parent-chat",
                "cron_job_id": 42,
                "heartbeat_enabled": True,
                "heartbeat_interval_minutes": 5,
                "forked_from_chat_id": "older-chat",
                "unread_count": 3,
            },
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "answer"},
                {"role": "user", "content": "second"},
            ],
            working_directory="/workspace/project",
        )

        clone_id = db.clone_chat_to_point(
            source_id,
            new_title="Alternative",
            up_to_message_index=2,
        )
        clone = db.get_chat(clone_id)

        assert clone is not None
        assert clone.id != source_id
        assert clone.title == "Alternative"
        assert clone.messages == [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer"},
        ]
        assert clone.config["model"] == "gpt-4"
        assert clone.config["tools"] == ["read_file"]
        for key in (
            "tool_approval_policy",
            "permission_mode",
            "platform",
            "parent_chat_id",
            "cron_job_id",
            "heartbeat_enabled",
            "heartbeat_interval_minutes",
            "forked_from_chat_id",
            "unread_count",
        ):
            assert key not in clone.config
        assert clone.working_directory == "/workspace/project"

    def test_link_chat_to_project_moves_direct_subagents(self, db):
        source = db.get_project_by_slug(ChatDatabase.DEFAULT_PROJECT_SLUG)
        target_id = db.create_project("Target", "target")
        parent_id = db.create_chat("Parent", {}, project_id=source.id)
        child_id = db.create_chat(
            "Sub-agent",
            {"platform": "subagent", "parent_chat_id": parent_id},
            chat_id="subagent-sub_test",
            project_id=source.id,
        )

        assert db.link_chat_to_project(parent_id, target_id) is True

        assert db.get_chat(parent_id).project_id == target_id
        assert db.get_chat(child_id).project_id == target_id
        assert db.get_subagent_chat_ids_for_parent_chat(parent_id) == [child_id]

    def test_move_all_chats_moves_stale_direct_subagents(self, db):
        source = db.get_project_by_slug(ChatDatabase.DEFAULT_PROJECT_SLUG)
        target_id = db.create_project("Target", "target")
        stale_id = db.create_project("Stale", "stale")
        parent_id = db.create_chat("Parent", {}, project_id=source.id)
        child_id = db.create_chat(
            "Sub-agent",
            {"platform": "subagent", "parent_chat_id": parent_id},
            chat_id="subagent-sub_stale",
            project_id=stale_id,
        )

        moved = db.move_all_chats(source.id, target_id)

        assert moved == 2
        assert db.get_chat(parent_id).project_id == target_id
        assert db.get_chat(child_id).project_id == target_id

    def test_list_subagent_task_records_includes_selected_child_chat(self, db):
        parent_id = db.create_chat("Parent", {})
        child_id = db.create_chat(
            "Sub-agent: inspect files",
            {
                "platform": "subagent",
                "parent_chat_id": parent_id,
                "subagent_task_id": "sub_12345678",
                "model": "test-model",
            },
            chat_id="subagent-sub_12345678",
        )

        by_parent = db.list_subagent_task_records(parent_chat_id=parent_id)
        by_child = db.list_subagent_task_records(parent_chat_id=child_id)

        assert by_parent == by_child
        assert by_child[0]["task_id"] == "sub_12345678"
        assert by_child[0]["parent_chat_id"] == parent_id
        assert by_child[0]["chat_id"] == child_id
        assert by_child[0]["description"] == "inspect files"

    def test_list_subagent_task_records_handles_legacy_child_metadata(self, db):
        child_id = db.create_chat(
            "Analyzing Claude Code and Suzent",
            {"platform": "subagent"},
            chat_id="subagent-sub_legacy",
        )

        by_child = db.list_subagent_task_records(parent_chat_id=child_id)

        assert by_child[0]["task_id"] == "sub_legacy"
        assert by_child[0]["parent_chat_id"] == ""
        assert by_child[0]["chat_id"] == child_id
        assert by_child[0]["description"] == "Analyzing Claude Code and Suzent"

    def test_list_subagent_task_records_filters_and_limits_in_database(self, db):
        parent_id = db.create_chat("Parent", {})
        for index in range(3):
            db.create_chat(
                f"Sub-agent: task {index}",
                {
                    "platform": "subagent",
                    "parent_chat_id": parent_id,
                    "subagent_task_id": f"sub_{index}",
                },
                chat_id=f"subagent-sub_{index}",
            )

        limited = db.list_subagent_task_records(parent_chat_id=parent_id, limit=2)
        selected = db.list_subagent_task_records(task_id="sub_1", limit=1)

        assert len(limited) == 2
        assert [record["task_id"] for record in selected] == ["sub_1"]

    def test_persisted_running_subagent_is_reported_as_interrupted(self, db):
        child_id = db.create_chat(
            "Sub-agent: interrupted",
            {
                "platform": "subagent",
                "subagent_task_id": "sub_interrupted",
                "subagent_status": "running",
            },
            chat_id="subagent-sub_interrupted",
        )

        record = db.list_subagent_task_records(task_id="sub_interrupted")[0]

        assert record["chat_id"] == child_id
        # An orphan is stopped, not failed: nothing went wrong with the run, the
        # process it was living in went away.
        assert record["status"] == "cancelled"
        assert record["error"] == "Stopped when the server restarted"

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

    def test_list_chats_uses_cached_message_summary(self, db):
        chat_id = db.create_chat(
            "Summary Chat",
            {},
            [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "Visible answer <details><summary>tool</summary>secret</details>",
                },
            ],
        )

        chats = db.list_chats()
        summary = next(chat for chat in chats if chat.id == chat_id)
        assert summary.messageCount == 1
        assert summary.lastMessage == "Visible answer"

        db.update_chat(
            chat_id,
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "First answer"},
                {"role": "assistant", "content": "Second answer"},
            ],
        )

        chats = db.list_chats()
        summary = next(chat for chat in chats if chat.id == chat_id)
        assert summary.messageCount == 2
        assert summary.lastMessage == "Second answer"

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

    def test_save_api_key_does_not_mutate_environment(self, db, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        assert db.save_api_key("OPENAI_API_KEY", "persisted-key") is True

        assert os.environ.get("OPENAI_API_KEY") is None
        assert db.get_api_key("OPENAI_API_KEY") == "persisted-key"

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

    def test_undecryptable_legacy_secret_keeps_api_keys_table(
        self, tmp_path, monkeypatch
    ):
        db_path = tmp_path / "legacy-bad-key.db"
        secret_db_path = tmp_path / "secrets.db"
        old_key = Fernet.generate_key()
        old_token = Fernet(old_key).encrypt(b"persisted-db-key").decode()
        monkeypatch.setenv("SUZENT_USER_CONFIG_PATH", str(tmp_path / "config.yaml"))
        monkeypatch.setenv("SUZENT_SECRET_DB_PATH", str(secret_db_path))
        monkeypatch.setenv("SUZENT_SECRET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("SUZENT_SECRET_BACKEND", "encrypted_sqlite")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

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
                "INSERT INTO api_keys VALUES (?, ?, '2026-01-01T00:00:00')",
                ("OPENAI_API_KEY", old_token),
            )

        db = ChatDatabase(str(db_path))

        assert "api_keys" in set(inspect(db.engine).get_table_names())
        assert secrets.get_secret_manager().has_backend_value("OPENAI_API_KEY") is False
        assert old_token not in secret_db_path.read_text(
            encoding="utf-8", errors="ignore"
        )

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


class TestAgentInboxOperations:
    def _create_agents(self, db):
        project_id = db.create_project("Inbox", "inbox")
        sender_id = db.create_chat("Sender", {}, project_id=project_id)
        target_id = db.create_chat("Target", {}, project_id=project_id)
        return sender_id, target_id

    def test_enqueue_is_idempotent(self, db):
        sender_id, target_id = self._create_agents(db)

        first, first_created = db.enqueue_agent_message(
            message_id="msg-1",
            sender_chat_id=sender_id,
            target_chat_id=target_id,
            content="Review this",
        )
        second, second_created = db.enqueue_agent_message(
            message_id="msg-1",
            sender_chat_id=sender_id,
            target_chat_id=target_id,
            content="Review this",
        )

        assert first_created is True
        assert second_created is False
        assert first["message_id"] == second["message_id"]
        assert len(db.list_agent_messages(target_chat_id=target_id)) == 1

    def test_remote_message_reuses_durable_queue_without_local_chat(self, db):
        sender_id, _target_id = self._create_agents(db)

        record, created = db.enqueue_agent_message(
            message_id="msg-remote",
            sender_chat_id=sender_id,
            target_chat_id="peer:peer-1",
            transport="suzent_peer",
            destination_peer_id="peer-1",
            kind="remote_agent_message",
            content="Run checks remotely",
        )
        claimed = db.claim_next_agent_message(worker_id="worker-1")

        assert created is True
        assert record["transport"] == "suzent_peer"
        assert record["destination_peer_id"] == "peer-1"
        assert claimed["message_id"] == "msg-remote"

    def test_existing_inbox_table_gains_transport_columns(self, tmp_path):
        db_path = tmp_path / "legacy-inbox.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE agent_inbox_messages (
                    message_id TEXT PRIMARY KEY,
                    sender_chat_id TEXT,
                    target_chat_id TEXT NOT NULL,
                    kind TEXT,
                    content TEXT NOT NULL,
                    payload JSON,
                    status TEXT,
                    attempts INTEGER,
                    max_attempts INTEGER,
                    available_at DATETIME,
                    lease_owner TEXT,
                    lease_until DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    delivered_at DATETIME,
                    last_error TEXT
                )
                """
            )

        migrated = ChatDatabase(str(db_path))
        columns = {
            column["name"]
            for column in inspect(migrated.engine).get_columns("agent_inbox_messages")
        }

        assert {"transport", "destination_peer_id"} <= columns
        migrated.engine.dispose()

    def test_claim_and_acknowledge_message(self, db):
        sender_id, target_id = self._create_agents(db)
        db.enqueue_agent_message(
            message_id="msg-claim",
            sender_chat_id=sender_id,
            target_chat_id=target_id,
            content="Run checks",
        )

        claimed = db.claim_next_agent_message(worker_id="worker-1")

        assert claimed["message_id"] == "msg-claim"
        assert claimed["status"] == "processing"
        assert claimed["attempts"] == 1
        assert db.acknowledge_agent_message("msg-claim", worker_id="worker-2") is False
        assert db.acknowledge_agent_message("msg-claim", worker_id="worker-1") is True
        assert (
            db.list_agent_messages(target_chat_id=target_id)[0]["status"] == "delivered"
        )

    def test_retry_releases_message_for_another_claim(self, db):
        sender_id, target_id = self._create_agents(db)
        db.enqueue_agent_message(
            message_id="msg-retry",
            sender_chat_id=sender_id,
            target_chat_id=target_id,
            content="Retry me",
        )
        db.claim_next_agent_message(worker_id="worker-1")

        assert db.retry_agent_message(
            "msg-retry",
            worker_id="worker-1",
            error="temporary failure",
            retry_delay_seconds=0,
        )
        claimed = db.claim_next_agent_message(worker_id="worker-2")

        assert claimed["message_id"] == "msg-retry"
        assert claimed["attempts"] == 2
        assert claimed["lease_owner"] == "worker-2"

    def test_claim_serializes_each_target_across_workers(self, db):
        sender_id, target_id = self._create_agents(db)
        other_target_id = db.create_chat(
            "Other target",
            {},
            project_id=db.get_chat(target_id).project_id,
        )
        for message_id, recipient in (
            ("msg-first", target_id),
            ("msg-same-target", target_id),
            ("msg-other-target", other_target_id),
        ):
            db.enqueue_agent_message(
                message_id=message_id,
                sender_chat_id=sender_id,
                target_chat_id=recipient,
                content=message_id,
            )

        first = db.claim_next_agent_message(worker_id="worker-1")
        second = db.claim_next_agent_message(worker_id="worker-2")
        third = db.claim_next_agent_message(worker_id="worker-3")

        assert first["message_id"] == "msg-first"
        assert second["message_id"] == "msg-other-target"
        assert third is None

    def test_expired_exhausted_message_becomes_failed(self, db):
        sender_id, target_id = self._create_agents(db)
        db.enqueue_agent_message(
            message_id="msg-exhausted",
            sender_chat_id=sender_id,
            target_chat_id=target_id,
            content="Fail me",
            max_attempts=1,
        )
        db.claim_next_agent_message(worker_id="worker-1", lease_seconds=1)
        with db._session() as session:
            message = session.get(AgentInboxMessageModel, "msg-exhausted")
            message.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(message)
            session.commit()

        assert db.claim_next_agent_message(worker_id="worker-2") is None
        record = db.list_agent_messages(target_chat_id=target_id)[0]
        assert record["status"] == "failed"
        assert record["lease_owner"] is None
