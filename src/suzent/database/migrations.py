import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy import inspect, text
from sqlmodel import select

from .models import (
    ChatModel,
)


class DatabaseMigrationMixin:
    def _run_migrations(self):
        """Run database migrations for new columns."""
        inspector = inspect(self.engine)

        # Migration: Add 'headers' column to 'mcp_servers' table
        if "mcp_servers" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("mcp_servers")]
            if "headers" not in columns:
                with self.engine.connect() as conn:
                    conn.execute(
                        text("ALTER TABLE mcp_servers ADD COLUMN headers TEXT")
                    )
                    conn.commit()

        # Migration: Add retry_count and drop legacy is_heartbeat from cron_jobs
        if "cron_jobs" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("cron_jobs")]
            with self.engine.connect() as conn:
                if "retry_count" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE cron_jobs ADD COLUMN retry_count INTEGER DEFAULT 0"
                        )
                    )
                if "is_heartbeat" in columns:
                    conn.execute(text("ALTER TABLE cron_jobs DROP COLUMN is_heartbeat"))
                conn.commit()

        # Migration: Add session lifecycle columns to 'chats' table
        if "chats" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("chats")]
            with self.engine.connect() as conn:
                if "last_active_at" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN last_active_at DATETIME")
                    )
                if "turn_count" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chats ADD COLUMN turn_count INTEGER DEFAULT 0"
                        )
                    )
                if "last_result_at" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN last_result_at DATETIME")
                    )
                if "working_directory" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN working_directory TEXT")
                    )
                if "state_revision" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chats ADD COLUMN state_revision INTEGER DEFAULT 0"
                        )
                    )
                if "finalized_revision" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chats ADD COLUMN finalized_revision INTEGER DEFAULT 0"
                        )
                    )
                if "state_stage" not in columns:
                    conn.execute(text("ALTER TABLE chats ADD COLUMN state_stage TEXT"))
                if "state_updated_at" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN state_updated_at DATETIME")
                    )
                conn.commit()

        # Migration: Add file_snapshot columns to retry_checkpoints
        if "retry_checkpoints" in inspector.get_table_names():
            columns = [
                col["name"] for col in inspector.get_columns("retry_checkpoints")
            ]
            with self.engine.connect() as conn:
                if "has_file_snapshot" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE retry_checkpoints ADD COLUMN has_file_snapshot BOOLEAN DEFAULT 0"
                        )
                    )
                if "file_snapshot" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE retry_checkpoints ADD COLUMN file_snapshot TEXT"
                        )
                    )
                conn.commit()

        # Migration: Ensure postprocess_jobs table exists (auto-created by SQLModel)
        # Verify it exists after create_all() runs
        if "postprocess_jobs" not in inspector.get_table_names():
            # This should not happen as SQLModel.metadata.create_all() already ran
            # but adding for safety
            with self.engine.connect() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS postprocess_jobs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job_id TEXT NOT NULL UNIQUE,
                            chat_id TEXT NOT NULL,
                            assigned_revision INTEGER NOT NULL,
                            current_revision INTEGER,
                            status TEXT DEFAULT 'pending',
                            outcome TEXT,
                            attempt INTEGER DEFAULT 1,
                            max_attempts INTEGER DEFAULT 3,
                            step_status_json TEXT,
                            started_at DATETIME,
                            finished_at DATETIME,
                            duration_ms INTEGER,
                            error_class TEXT,
                            error_message TEXT,
                            created_at DATETIME,
                            updated_at DATETIME,
                            FOREIGN KEY(chat_id) REFERENCES chats(id)
                        )
                        """
                    )
                )
                # Create indexes for query performance
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_postprocess_jobs_chat_id ON postprocess_jobs(chat_id)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_postprocess_jobs_status ON postprocess_jobs(status)"
                    )
                )
                conn.commit()

        # Migration: Add cache token columns to cost_ledger and chat_cost_summary
        if "cost_ledger" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("cost_ledger")]
            with self.engine.connect() as conn:
                if "cache_write_tokens" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE cost_ledger ADD COLUMN cache_write_tokens INTEGER DEFAULT 0"
                        )
                    )
                if "cache_read_tokens" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE cost_ledger ADD COLUMN cache_read_tokens INTEGER DEFAULT 0"
                        )
                    )
                conn.commit()

        if "chat_cost_summary" in inspector.get_table_names():
            columns = [
                col["name"] for col in inspector.get_columns("chat_cost_summary")
            ]
            with self.engine.connect() as conn:
                if "total_cache_write_tokens" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chat_cost_summary ADD COLUMN total_cache_write_tokens INTEGER DEFAULT 0"
                        )
                    )
                if "total_cache_read_tokens" not in columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chat_cost_summary ADD COLUMN total_cache_read_tokens INTEGER DEFAULT 0"
                        )
                    )
                conn.commit()

        # Migration: Persist the latest rich context/usage payload per chat for UI display.
        if "chats" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("chats")]
            with self.engine.connect() as conn:
                if "context_usage" not in columns:
                    conn.execute(
                        text("ALTER TABLE chats ADD COLUMN context_usage JSON")
                    )
                conn.commit()

        # Migration: Add projects table and chats.project_id FK.
        # projects table is created by SQLModel.metadata.create_all() above,
        # but chats.project_id needs an explicit ALTER on existing databases.
        if "chats" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("chats")]
            if "project_id" not in columns:
                with self.engine.connect() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE chats ADD COLUMN project_id TEXT REFERENCES projects(id)"
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_chats_project_id ON chats(project_id)"
                        )
                    )
                    conn.commit()

    def _migrate_static_config_from_db(self) -> None:
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        legacy_tables = {"user_preferences", "memory_config", "api_keys"} & tables
        if not legacy_tables:
            return

        from suzent.core.user_config import UserConfigStore

        store = UserConfigStore()
        migrated = False
        drop_tables: set[str] = set()

        try:
            with self.engine.connect() as conn:
                did_migrate, can_drop = self._migrate_legacy_user_preferences(
                    conn, store, legacy_tables
                )
                migrated |= did_migrate
                if can_drop:
                    drop_tables.add("user_preferences")

                did_migrate, can_drop = self._migrate_legacy_memory_config(
                    conn, store, legacy_tables
                )
                migrated |= did_migrate
                if can_drop:
                    drop_tables.add("memory_config")

                did_migrate, can_drop = self._migrate_legacy_api_keys(
                    conn, store, legacy_tables
                )
                migrated |= did_migrate
                if can_drop:
                    drop_tables.add("api_keys")

                self._drop_legacy_static_tables(conn, drop_tables)
                conn.commit()

            if migrated:
                from suzent.logger import logger

                logger.info("Migrated legacy static config out of SQLite")
        except Exception as exc:
            from suzent.logger import logger

            logger.warning(
                "Failed to migrate legacy static config from SQLite: {}", exc
            )

    def _migrate_legacy_user_preferences(
        self, conn: Any, store: Any, legacy_tables: set[str]
    ) -> tuple[bool, bool]:
        if "user_preferences" not in legacy_tables:
            return False, False

        row = (
            conn.execute(
                text(
                    """
                    SELECT model, agent, tools, memory_enabled,
                           sandbox_enabled, sandbox_volumes
                    FROM user_preferences WHERE id = 1
                    """
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return False, True
        if store._get_section("user_preferences"):
            from suzent.logger import logger

            logger.warning(
                "Keeping legacy user_preferences table because user config already exists"
            )
            return False, False

        store.save_user_preferences(
            {
                "model": row["model"],
                "agent": row["agent"],
                "tools": self._decode_json_value(row["tools"]),
                "memory_enabled": self._bool_or_none(row["memory_enabled"]),
                "sandbox_enabled": self._bool_or_none(row["sandbox_enabled"]),
                "sandbox_volumes": self._decode_json_value(row["sandbox_volumes"]),
            }
        )
        return True, True

    def _migrate_legacy_memory_config(
        self, conn: Any, store: Any, legacy_tables: set[str]
    ) -> tuple[bool, bool]:
        if "memory_config" not in legacy_tables:
            return False, False

        row = (
            conn.execute(
                text(
                    """
                    SELECT embedding_model, extraction_model
                    FROM memory_config WHERE id = 1
                    """
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return False, True
        if store.get_memory_config():
            from suzent.logger import logger

            logger.warning(
                "Keeping legacy memory_config table because user config already exists"
            )
            return False, False

        store.save_memory_config(
            {
                "embedding_model": row["embedding_model"],
                "extraction_model": row["extraction_model"],
            }
        )
        return True, True

    def _migrate_legacy_api_keys(
        self, conn: Any, store: Any, legacy_tables: set[str]
    ) -> tuple[bool, bool]:
        if "api_keys" not in legacy_tables:
            return False, False

        migrated = False
        can_drop = True
        rows = conn.execute(text("SELECT key, value FROM api_keys")).mappings().all()
        for row in rows:
            key = row["key"]
            value = row["value"]
            if not key or not value:
                continue
            if key.startswith("_"):
                if store.get_config_blob(key) is None:
                    store.save_config_blob(key, value)
                    migrated = True
                else:
                    from suzent.logger import logger

                    logger.warning(
                        "Keeping legacy api_keys table because config blob '{}' already exists",
                        key,
                    )
                    can_drop = False
                continue
            secret_migrated, secret_can_drop = self._migrate_secret_to_backend(
                key, value
            )
            migrated |= secret_migrated
            can_drop &= secret_can_drop
        return migrated, can_drop

    @staticmethod
    def _drop_legacy_static_tables(conn: Any, legacy_tables: set[str]) -> None:
        for table in legacy_tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))

    @staticmethod
    def _decode_json_value(value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _bool_or_none(value: Any) -> Optional[bool]:
        if value is None:
            return None
        return bool(value)

    @staticmethod
    def _parse_config_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        return datetime.now()

    def _migrate_secret_to_backend(self, key: str, value: str) -> tuple[bool, bool]:
        from suzent.core.secrets import get_secret_manager

        secret_manager = get_secret_manager()
        if secret_manager.has_backend_value(key):
            from suzent.logger import logger

            logger.warning(
                "Keeping legacy api_keys table because secret '{}' already exists",
                key,
            )
            return False, False

        secret = self._decrypt_legacy_secret(key, value)
        if secret is None:
            return False, False
        secret_manager.set_backend_only(key, secret)
        return True, True

    def _decrypt_legacy_secret(self, key: str, value: str) -> Optional[str]:
        try:
            from cryptography.fernet import Fernet, InvalidToken
            from suzent.config import DATA_DIR

            raw_keys = []
            if env_key := os.environ.get("SUZENT_SECRET_KEY"):
                raw_keys.append(env_key.encode())
            key_file = DATA_DIR / ".secret_key"
            if key_file.exists():
                raw_keys.append(key_file.read_bytes().strip())

            for raw_key in raw_keys:
                try:
                    return Fernet(raw_key).decrypt(value.encode()).decode()
                except InvalidToken:
                    continue
        except Exception:
            pass

        if self._looks_like_fernet_token(value):
            from suzent.logger import logger

            logger.warning(
                "Keeping legacy api_keys table because secret '{}' could not be decrypted",
                key,
            )
            return None
        return value

    @staticmethod
    def _looks_like_fernet_token(value: str) -> bool:
        try:
            token = base64.urlsafe_b64decode(value.encode())
        except Exception:
            return False
        return bool(token) and token[0] == 0x80

    # -------------------------------------------------------------------------
    # Project Operations
    # -------------------------------------------------------------------------

    def _migrate_legacy_session_dirs(self) -> None:
        """Flatten legacy per-chat directories into the project root.

        Handles three legacy shapes:

        1. ``sandbox_data_path/sessions/{chat_id}/...`` (pre-project layout)
        2. ``sandbox_data_path/projects/{slug}/chats/{chat_id}/...``
           (intermediate layout — earlier migration step)
        3. ``sandbox_data_path/shared/memory/sessions/{chat_id[:32]}/context.md``
           (legacy memory context location)

        After migration the project directory contains a flat layout::

            projects/{slug}/
              heartbeat.md
              context.md
              uploads/<files, prefixed with {chat_id[:8]}_ on collision>
              images/<files, prefixed with {chat_id[:8]}_ on collision>

        Each chat's files are merged into the project. On filename collision
        within ``uploads/`` or ``images/`` the moved file is prefixed with the
        short chat id so nothing is silently dropped. Single-file artifacts
        (heartbeat.md, context.md) follow first-wins: the first chat's file
        becomes the project's; subsequent chats' files are kept on disk under
        a ``.from-chat-{chat_id[:8]}`` suffix so they can be reviewed.

        Runs once per startup. Failures are logged but do not abort startup.
        """
        from suzent.logger import logger

        try:
            from suzent.config import CONFIG
        except Exception:
            return

        import shutil

        sandbox_root = Path(CONFIG.sandbox_data_path)
        projects_root = sandbox_root / "projects"

        # Phase 1: collect (chat_id, source_dir) pairs from legacy layouts.
        sources: List[tuple[str, Path]] = []

        # Legacy shape 1: sessions/{chat_id}/
        sessions_root = sandbox_root / "sessions"
        if sessions_root.exists() and sessions_root.is_dir():
            for d in sessions_root.iterdir():
                if d.is_dir():
                    sources.append((d.name, d))

        # Legacy shape 2: projects/{slug}/chats/{chat_id}/
        if projects_root.exists():
            for project_dir in projects_root.iterdir():
                chats_dir = project_dir / "chats"
                if chats_dir.exists() and chats_dir.is_dir():
                    for d in chats_dir.iterdir():
                        if d.is_dir():
                            sources.append((d.name, d))

        moved_chats = 0
        for chat_id, source_dir in sources:
            try:
                if self._flatten_chat_dir_into_project(chat_id, source_dir):
                    moved_chats += 1
            except Exception as e:
                logger.warning("Failed to flatten chat dir {}: {}", source_dir, e)

        if moved_chats:
            logger.info(
                "Flattened {} legacy chat dir(s) into project roots", moved_chats
            )

        # Legacy shape 3: shared/memory/sessions/{chat_id[:32]}/context.md
        mem_sessions = sandbox_root / "shared" / "memory" / "sessions"
        if mem_sessions.exists() and mem_sessions.is_dir():
            moved_ctx = 0
            for d in mem_sessions.iterdir():
                if not d.is_dir():
                    continue
                ctx = d / "context.md"
                if not ctx.exists():
                    continue
                # d.name is chat_id[:32] — find a chat whose id starts with it
                short_id = d.name
                chat_id = self._find_chat_id_by_prefix(short_id)
                if not chat_id:
                    logger.debug(
                        "No chat matches legacy memory dir {}; leaving in place",
                        short_id,
                    )
                    continue
                slug = self.get_chat_project_slug(chat_id)
                project_dir = projects_root / slug
                project_dir.mkdir(parents=True, exist_ok=True)
                dest = project_dir / "context.md"
                if dest.exists():
                    # First-wins; keep this chat's context under a backup name
                    backup = project_dir / f"context.from-chat-{chat_id[:8]}.md"
                    if not backup.exists():
                        shutil.move(str(ctx), str(backup))
                else:
                    shutil.move(str(ctx), str(dest))
                # Clean up the empty legacy dir
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except Exception:
                    pass
                moved_ctx += 1
            if moved_ctx:
                logger.info("Migrated {} legacy memory context file(s)", moved_ctx)
            # Drop the empty sessions root
            try:
                if mem_sessions.exists() and not any(mem_sessions.iterdir()):
                    mem_sessions.rmdir()
            except Exception:
                pass

        # Drop empty top-level legacy dirs
        for empty_root in (sessions_root,):
            try:
                if empty_root.exists() and not any(empty_root.iterdir()):
                    empty_root.rmdir()
            except Exception:
                pass

        # Drop empty projects/{slug}/chats/ directories
        if projects_root.exists():
            for project_dir in projects_root.iterdir():
                chats_dir = project_dir / "chats"
                try:
                    if chats_dir.exists() and not any(chats_dir.iterdir()):
                        chats_dir.rmdir()
                except Exception:
                    pass

    def _flatten_chat_dir_into_project(self, chat_id: str, source_dir: Path) -> bool:
        """Move the contents of a legacy chat directory into its project root.

        Returns True if at least one file was moved. See _migrate_legacy_session_dirs
        for the collision/merge rules.
        """
        import shutil
        from suzent.logger import logger

        if not source_dir.exists():
            return False

        slug = self.get_chat_project_slug(chat_id)
        from suzent.config import CONFIG

        project_dir = Path(CONFIG.sandbox_data_path) / "projects" / slug
        project_dir.mkdir(parents=True, exist_ok=True)

        short = chat_id[:8]
        moved_any = False

        for entry in list(source_dir.iterdir()):
            try:
                if entry.is_dir() and entry.name in ("uploads", "images"):
                    # Merge contents file-by-file, prefixing collisions with chat id
                    dest_dir = project_dir / entry.name
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    for f in list(entry.iterdir()):
                        target = dest_dir / f.name
                        if target.exists():
                            target = dest_dir / f"{short}_{f.name}"
                        if target.exists():
                            # Even the prefixed name exists; skip to avoid clobber
                            logger.debug(
                                "Skipping {} for chat {}: collision even after prefix",
                                f,
                                short,
                            )
                            continue
                        shutil.move(str(f), str(target))
                        moved_any = True
                    # Remove the empty source subdir
                    try:
                        if not any(entry.iterdir()):
                            entry.rmdir()
                    except Exception:
                        pass
                elif entry.is_file() and entry.name in ("heartbeat.md", "context.md"):
                    # Single-file artifacts: first-wins, keep extras as backup
                    dest = project_dir / entry.name
                    if dest.exists():
                        backup = (
                            project_dir
                            / f"{entry.stem}.from-chat-{short}{entry.suffix}"
                        )
                        if not backup.exists():
                            shutil.move(str(entry), str(backup))
                            moved_any = True
                    else:
                        shutil.move(str(entry), str(dest))
                        moved_any = True
                else:
                    # Unknown file/dir — move with prefix on collision
                    target = project_dir / entry.name
                    if target.exists():
                        target = project_dir / f"{short}_{entry.name}"
                    if not target.exists():
                        shutil.move(str(entry), str(target))
                        moved_any = True
            except Exception as e:
                logger.warning("Failed migrating {} from chat {}: {}", entry, short, e)

        # Remove the now-empty source dir
        try:
            if source_dir.exists() and not any(source_dir.iterdir()):
                source_dir.rmdir()
        except Exception:
            pass

        return moved_any

    def _find_chat_id_by_prefix(self, prefix: str) -> Optional[str]:
        """Resolve a chat id from its first 32 chars (used by legacy memory dirs)."""
        with self._session() as session:
            for chat in session.exec(
                select(ChatModel).where(ChatModel.id.startswith(prefix))
            ).all():
                return chat.id
        return None
