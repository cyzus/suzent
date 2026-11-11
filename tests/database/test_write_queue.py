import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from suzent.database import ChatDatabase
from suzent.database import write_queue


@pytest.mark.parametrize("separate_engine", [False, True])
def test_slow_save_queues_other_writers_but_not_readers(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch, separate_engine: bool
) -> None:
    db = temp_db
    first_id = db.create_chat("First", {})
    second_id = db.create_chat("Second", {})
    other = ChatDatabase(str(db.db_path)) if separate_engine else db

    def short_timeout(connection, _record) -> None:
        connection.execute("PRAGMA busy_timeout=1")

    for engine in {db.engine, other.engine}:
        engine.dispose()
        event.listen(engine, "connect", short_timeout)

    monkeypatch.setattr(write_queue, "_NOTICE_SECONDS", 0.05)
    entered = threading.Event()
    release = threading.Event()
    queued = threading.Event()
    records: list[str] = []
    original = db.chat_log.prepare

    def slow_prepare(chat_id: str, *args, **kwargs):
        if chat_id == first_id:
            entered.set()
            assert release.wait(5), "writer was never released"
        return original(chat_id, *args, **kwargs)

    def warning(message: str, *args) -> None:
        records.append(message.format(*args))
        if "queued" in message:
            queued.set()

    monkeypatch.setattr(db.chat_log, "prepare", slow_prepare)
    monkeypatch.setattr(write_queue.logger, "warning", warning)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(db.update_chat, first_id, title="Saved first")
        try:
            assert entered.wait(3)
            second = executor.submit(other.update_chat, second_id, title="Saved second")
            assert queued.wait(3), "second writer did not enter the application queue"
            assert not second.done()
            assert other.get_chat(second_id).title == "Second"
        finally:
            release.set()
        assert first.result(timeout=3)
        assert second.result(timeout=3)

    assert db.get_chat(first_id).title == "Saved first"
    assert other.get_chat(second_id).title == "Saved second"
    assert any("owner_caller=suzent.database.chats:" in record for record in records)
    assert any("released" in record for record in records)
    assert all(
        "Saved first" not in record and "Saved second" not in record
        for record in records
    )
    assert db.chat_log_differences(db.chat_log) == {}
    if separate_engine:
        other.engine.dispose()


@pytest.mark.parametrize("invalidate", [False, True])
def test_failed_writer_releases_queue(temp_db: ChatDatabase, invalidate: bool) -> None:
    with temp_db.engine.connect() as conn:
        conn.execute(text("UPDATE chats SET title = title WHERE 0"))
        if invalidate:
            conn.invalidate()
        else:
            conn.rollback()

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(temp_db.create_chat, "After failure", {})
        assert result.result(timeout=3)


def test_uncoordinated_writer_is_reported_and_does_not_strand_queue(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id = temp_db.create_chat("Original", {})
    temp_db.engine.dispose()

    def short_timeout(connection, _record) -> None:
        connection.execute("PRAGMA busy_timeout=1")

    event.listen(temp_db.engine, "connect", short_timeout)
    records: list[str] = []
    monkeypatch.setattr(
        write_queue.logger,
        "warning",
        lambda message, *args: records.append(message.format(*args)),
    )
    with sqlite3.connect(temp_db.db_path) as external:
        external.execute("UPDATE chats SET title = title WHERE 0")
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(temp_db.update_chat, chat_id, title="Queued")
            with pytest.raises(OperationalError, match="locked"):
                result.result(timeout=3)
        external.rollback()

    assert any("outside the write queue" in record for record in records)
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(temp_db.update_chat, chat_id, title="Recovered").result(
            timeout=3
        )
    assert temp_db.get_chat(chat_id).title == "Recovered"
    assert temp_db.chat_log_differences(temp_db.chat_log) == {}


def test_nested_writer_fails_without_deadlocking_or_releasing_outer_writer(
    temp_db: ChatDatabase,
) -> None:
    with temp_db.engine.connect() as outer:
        outer.execute(text("UPDATE chats SET title = title WHERE 0"))
        with temp_db.engine.connect() as inner:
            with pytest.raises(RuntimeError, match="Nested SQLite write connections"):
                inner.execute(text("UPDATE chats SET title = title WHERE 0"))
        outer.execute(text("UPDATE chats SET title = title WHERE 0"))
        outer.commit()

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(temp_db.create_chat, "After nested writer", {}).result(
            timeout=3
        )
