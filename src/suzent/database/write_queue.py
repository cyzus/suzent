"""Serialize SQLite writers before they spend the connection's busy timeout."""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine

from suzent.logger import get_logger

logger = get_logger(__name__)

_WRITER_KEY = "suzent_sqlite_writer"
_NOTICE_SECONDS = 1.0
_queues: WeakValueDictionary[str, SQLiteWriteQueue] = WeakValueDictionary()
_queues_lock = threading.Lock()


def _caller() -> str:
    frame = sys._getframe(1)
    callers: list[str] = []
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if module.startswith("suzent.") and module != __name__:
            callers.append(f"{module}:{frame.f_code.co_name}:{frame.f_lineno}")
            if len(callers) == 3:
                break
        frame = frame.f_back
    return " <- ".join(callers) or "external"


class SQLiteWriteQueue:
    """One writer per database file, shared by engines in this process."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._owner: object | None = None
        self._thread: int | None = None
        self._origin = ""
        self._started = 0.0
        self._waiting: deque[object] = deque()

    def acquire(self, token: object, origin: str) -> None:
        started = time.monotonic()
        noticed = False
        with self._condition:
            if self._thread == threading.get_ident():
                raise RuntimeError(
                    "Nested SQLite write connections: "
                    f"{origin} is waiting on {self._origin} in the same thread"
                )
            self._waiting.append(token)
            try:
                while self._owner is not None or self._waiting[0] is not token:
                    self._condition.wait(_NOTICE_SECONDS)
                    if self._owner is not None and not noticed:
                        logger.warning(
                            "[SQLiteWrite] queued pid={} thread={} caller={} "
                            "wait_s={:.3f} owner_thread={} owner_caller={} held_s={:.3f}",
                            os.getpid(),
                            threading.get_ident(),
                            origin,
                            time.monotonic() - started,
                            self._thread,
                            self._origin,
                            time.monotonic() - self._started,
                        )
                        noticed = True
            except BaseException:
                self._waiting.remove(token)
                self._condition.notify_all()
                raise
            self._waiting.popleft()
            self._owner = token
            self._thread = threading.get_ident()
            self._origin = origin
            self._started = time.monotonic()

    def release(self, token: object) -> None:
        with self._condition:
            if self._owner is not token:
                return
            held = time.monotonic() - self._started
            if held >= _NOTICE_SECONDS:
                logger.warning(
                    "[SQLiteWrite] released pid={} thread={} caller={} held_s={:.3f}",
                    os.getpid(),
                    self._thread,
                    self._origin,
                    held,
                )
            self._owner = None
            self._thread = None
            self._condition.notify_all()


def configure_write_queue(engine: Engine, db_path: Path) -> None:
    key = os.path.normcase(str(db_path.resolve()))
    with _queues_lock:
        queue = _queues.get(key)
        if queue is None:
            queue = SQLiteWriteQueue()
            _queues[key] = queue

    def before_execute(
        conn: Connection,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        if _WRITER_KEY in conn.info:
            return
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if not (
            context.isinsert
            or context.isupdate
            or context.isdelete
            or context.isddl
            or verb
            in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER"}
        ):
            return
        token = object()
        queue.acquire(token, _caller())
        conn.info[_WRITER_KEY] = token

    def release(_dbapi_connection: Any, record: Any, *_args: Any) -> None:
        token = record.info.pop(_WRITER_KEY, None)
        if token is not None:
            queue.release(token)

    def handle_error(context: Any) -> None:
        code = getattr(context.original_exception, "sqlite_errorcode", 0)
        if code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            logger.warning(
                "[SQLiteWrite] SQLite lock conflict pid={} thread={} caller={} "
                "code={}; check other processes or connections outside the write queue",
                os.getpid(),
                threading.get_ident(),
                _caller(),
                code,
            )

    event.listen(engine, "before_cursor_execute", before_execute)
    # Pool check-in follows the actual DBAPI commit/rollback. SQLAlchemy's
    # connection commit event runs *before* commit and would release too early.
    event.listen(engine, "checkin", release)
    event.listen(engine, "invalidate", release)
    event.listen(engine, "handle_error", handle_error)
