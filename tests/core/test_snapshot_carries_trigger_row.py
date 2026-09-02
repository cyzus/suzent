"""A cron turn's provenance must become durable with the history it describes.

The reminder block stops being authenticatable once the process restarts, so a
row written later cannot be vouched for. Writing it separately loses either way:
the process can exit between the two writes, or a stale finalizer can replace
`messages` wholesale afterwards. Both are closed by committing inside the
transaction that advances the revision.
"""

import pytest

from suzent.core.chat_processor import ChatProcessor

TS = "2026-09-02T04:00:00+00:00"


def _row(label="Cron: digest", ts=TS):
    return {
        "role": "system_triggered",
        "content": label,
        "trigger_origin": "runtime",
        "timestamp": ts,
    }


class _FakeDB:
    def __init__(self):
        self.snapshot_calls = []
        self.update_calls = []

    def commit_snapshot_state(self, chat_id, agent_state, append_display_messages=None):
        self.snapshot_calls.append((chat_id, list(append_display_messages or [])))
        return 7

    def update_chat(self, chat_id, **kwargs):
        self.update_calls.append((chat_id, kwargs))


@pytest.fixture
def db(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: fake)
    monkeypatch.setattr(
        "suzent.core.chat_processor.serialize_state",
        lambda messages, model_id=None, tool_names=None: b"state",
    )
    return fake


@pytest.mark.asyncio
async def test_trigger_rows_ride_the_snapshot_transaction(db):
    await ChatProcessor()._persist_agent_state_snapshot(
        chat_id="chat-1",
        messages=[],
        model_id=None,
        tool_names=[],
        append_display_messages=[_row()],
    )

    assert db.snapshot_calls == [("chat-1", [_row()])]
    assert db.update_calls == [], "must not be a second, unrevisioned write"


@pytest.mark.asyncio
async def test_ordinary_turns_append_nothing(db):
    await ChatProcessor()._persist_agent_state_snapshot(
        chat_id="chat-1", messages=[], model_id=None, tool_names=[]
    )

    assert db.snapshot_calls == [("chat-1", [])]


# --- the transaction itself -------------------------------------------------


@pytest.fixture
def chat_db(tmp_path):
    from suzent.database import ChatDatabase

    database = ChatDatabase(str(tmp_path / "t.db"))
    try:
        yield database
    finally:
        try:
            database.engine.dispose()
        except Exception:
            pass


def _new_chat(database):
    """create_chat returns the id, not the row."""
    return database.create_chat(title="t", config={})


def test_the_row_and_the_revision_commit_together(chat_db):
    db = chat_db
    chat_id = _new_chat(db)

    revision = db.commit_snapshot_state(
        chat_id, b"state", append_display_messages=[_row()]
    )

    stored = db.get_chat(chat_id)
    assert revision == (stored.state_revision or 0)
    assert stored.messages == [_row()]
    assert stored.agent_state == b"state"


def test_a_stale_finalizer_cannot_drop_the_row(chat_db):
    """The finalizer's revision check now fails, because appending advanced it."""
    db = chat_db
    chat_id = _new_chat(db)
    stale_revision = db.get_chat(chat_id).state_revision or 0

    db.commit_snapshot_state(chat_id, b"state", append_display_messages=[_row()])
    finalized = db.finalize_state_if_revision_matches(
        chat_id=chat_id,
        expected_revision=stale_revision,
        agent_state=b"older",
        messages=[{"role": "user", "content": "would clobber"}],
    )

    assert finalized is False
    assert db.get_chat(chat_id).messages == [_row()]


def test_appending_is_idempotent(chat_db):
    db = chat_db
    chat_id = _new_chat(db)

    db.commit_snapshot_state(chat_id, b"a", append_display_messages=[_row()])
    db.commit_snapshot_state(chat_id, b"b", append_display_messages=[_row()])

    assert db.get_chat(chat_id).messages == [_row()]


def test_existing_rows_are_kept(chat_db):
    db = chat_db
    chat_id = _new_chat(db)
    db.update_chat(chat_id, messages=[{"role": "user", "content": "earlier"}])

    db.commit_snapshot_state(chat_id, b"state", append_display_messages=[_row()])

    assert db.get_chat(chat_id).messages == [
        {"role": "user", "content": "earlier"},
        _row(),
    ]


def test_no_rows_leaves_messages_untouched(chat_db):
    db = chat_db
    chat_id = _new_chat(db)
    db.update_chat(chat_id, messages=[{"role": "user", "content": "earlier"}])

    db.commit_snapshot_state(chat_id, b"state")

    assert db.get_chat(chat_id).messages == [{"role": "user", "content": "earlier"}]


# --- the heartbeat exclusion ------------------------------------------------


class _Part:
    def __init__(self, stamp=None):
        self.timestamp = stamp


def test_a_cron_turn_yields_a_stamped_row():
    from datetime import datetime, timezone

    from suzent.core.chat_processor import trigger_rows_for_snapshot

    stamp = datetime(2026, 9, 2, 4, tzinfo=timezone.utc)
    rows = trigger_rows_for_snapshot("Cron: digest", False, _Part(stamp))

    assert rows == [_row(ts=stamp.isoformat())]


def test_a_heartbeat_turn_yields_nothing():
    """_persist_state sets skip_messages=is_heartbeat deliberately, and rollback
    only runs after a successful HEARTBEAT_OK — so a row persisted here would
    survive every failure path and leave the internal prompt in the transcript.
    An earlier attempt shipped exactly that."""
    from suzent.core.chat_processor import trigger_rows_for_snapshot

    assert trigger_rows_for_snapshot("Heartbeat: check inbox", True, _Part()) == []


def test_an_ordinary_turn_yields_nothing():
    from suzent.core.chat_processor import trigger_rows_for_snapshot

    assert trigger_rows_for_snapshot(None, False, _Part()) == []
    assert trigger_rows_for_snapshot("", False, _Part()) == []


def test_a_part_without_a_timestamp_still_yields_a_row():
    from suzent.core.chat_processor import trigger_rows_for_snapshot

    rows = trigger_rows_for_snapshot("Cron: digest", False, _Part())

    assert rows and "timestamp" not in rows[0]
