from sqlalchemy import text
from sqlmodel import Session

from suzent.database import ChatDatabase
from suzent.database.base import BUSY_TIMEOUT_MS
from suzent.database.models import chat_exists


def test_connections_use_wal_and_wait_for_other_writers(temp_db: ChatDatabase) -> None:
    with temp_db.engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == BUSY_TIMEOUT_MS


def test_chat_exists_checks_by_id(temp_db: ChatDatabase) -> None:
    chat_id = temp_db.create_chat("T", {}, [{"role": "user", "content": "hi"}])
    with Session(temp_db.engine) as session:
        assert chat_exists(session, chat_id)
        assert not chat_exists(session, "missing")
