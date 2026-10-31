from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

# How long a write waits for another writer before failing as locked.
BUSY_TIMEOUT_MS = 15_000


def _configure_connection(dbapi_connection, _record) -> None:
    """WAL lets reads run while an agent turn writes a long chat; without it
    the board and chat list wait behind every save. Writers still queue, so
    they wait longer than the 5s default before failing as locked.
    Under WAL, ``synchronous=NORMAL`` can lose the last commits on power loss
    but never corrupts the file, and chats replay those from their fsynced
    JSONL logs."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


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
        event.listen(self.engine, "connect", _configure_connection)

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
