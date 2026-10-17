from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine


class ChatDatabaseBase:
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Use data directory from config if available, otherwise relative to project
            try:
                from suzent.config import DATA_DIR

                self.db_path = DATA_DIR / "chats.db"
            except ImportError:
                self.db_path = Path(".suzent/chats.db")
        else:
            self.db_path = Path(db_path)

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # If db_path is a directory (Docker mount issue), remove it and create file
        if self.db_path.is_dir():
            import shutil

            shutil.rmtree(self.db_path)

        # Create engine with SQLite
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # Create all tables
        SQLModel.metadata.create_all(self.engine)

        # Run migrations for new columns
        self._run_migrations()
        self._migrate_static_config_from_db()
        self._ensure_default_project()
        self._migrate_legacy_session_dirs()
        self._init_chat_search()
        self._repair_stale_chat_summaries()

        from .chat_log import ChatEventLog, default_log_root

        # Each chat's JSONL log is its source of truth; chats.db indexes them.
        self.chat_log = ChatEventLog(default_log_root(self.db_path))
        # Before anything can write: a write diffs the row against its log, so
        # a log still ahead of its row from a crash would otherwise be undone.
        self.reconcile_chat_logs()

    def _session(self) -> Session:
        """Create a new database session."""
        return Session(self.engine)
