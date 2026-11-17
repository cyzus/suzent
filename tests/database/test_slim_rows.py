"""The chats row holds metadata only; messages and agent state live in the log."""

import json

import pytest
from sqlalchemy import text
from sqlmodel import Session

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from suzent.core.agent_serializer import serialize_state
from suzent.database import ChatDatabase, ChatModel

MESSAGES = [
    {"role": "user", "content": "你好世界"},
    {"role": "assistant", "content": "hello there"},
]


def _state(turns: int) -> bytes:
    messages = []
    for index in range(turns):
        messages.append(ModelRequest(parts=[UserPromptPart(content=f"q{index}")]))
        messages.append(ModelResponse(parts=[TextPart(content=f"a{index}")]))
    return serialize_state(messages, model_id="test:model", tool_names=["bash"])


def _reopen(db: ChatDatabase) -> ChatDatabase:
    db.engine.dispose()
    return ChatDatabase(str(db.db_path))


def _assert_log_matches(db: ChatDatabase) -> None:
    assert db.chat_log_differences(db.chat_log) == {}


def _raw_row(db: ChatDatabase, chat_id: str) -> tuple[str, bytes | None]:
    with db.engine.connect() as conn:
        return conn.execute(
            text("SELECT messages, agent_state FROM chats WHERE id = :id"),
            {"id": chat_id},
        ).one()


def _assert_slim(db: ChatDatabase, chat_id: str) -> None:
    messages, agent_state = _raw_row(db, chat_id)
    assert json.loads(messages) == []
    assert agent_state is None


def test_writes_leave_the_row_slim(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(
        title="t", config={}, messages=MESSAGES[:1], agent_state=_state(1)
    )
    _assert_slim(db, chat_id)

    db.update_chat(chat_id, messages=MESSAGES, agent_state=_state(2))
    db.append_chat_message(chat_id, {"role": "user", "content": "more"})
    _assert_slim(db, chat_id)

    chat = db.get_chat(chat_id)
    assert [m["content"] for m in chat.messages] == ["你好世界", "hello there", "more"]
    assert chat.agent_state is not None
    assert db.get_chat(chat_id, include_agent_state=False).messages == chat.messages
    _assert_log_matches(db)


def test_messages_survive_a_reopen(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(
        title="t", config={}, messages=MESSAGES, agent_state=_state(1)
    )
    db = _reopen(db)
    try:
        _assert_slim(db, chat_id)
        chat = db.get_chat(chat_id)
        assert [m["content"] for m in chat.messages] == ["你好世界", "hello there"]
        assert chat.agent_state is not None
    finally:
        db.engine.dispose()


def test_upgrade_slims_full_rows_and_empties_the_legacy_index(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(
        title="t", config={}, messages=MESSAGES, agent_state=_state(1)
    )
    with db.engine.begin() as conn:
        # How an older version leaves things: full row, position in the old table.
        conn.execute(
            text("UPDATE chats SET messages = :m, agent_state = :s WHERE id = :id"),
            {"m": json.dumps(MESSAGES), "s": _state(1), "id": chat_id},
        )
        conn.execute(
            text("INSERT INTO chat_log_index SELECT * FROM chat_log_positions")
        )
        conn.execute(text("DELETE FROM chat_log_positions"))

    db = _reopen(db)
    try:
        _assert_slim(db, chat_id)
        with db.engine.connect() as conn:
            # An older version finds no positions and replays every log in full.
            assert (
                conn.execute(text("SELECT count(*) FROM chat_log_index")).scalar() == 0
            )
        assert len(db.get_chat(chat_id).messages) == 2
        _assert_log_matches(db)
    finally:
        db.engine.dispose()


def test_short_queries_search_message_text(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="untitled", config={}, messages=MESSAGES)
    db.create_chat(title="other", config={}, messages=[])

    assert [c.id for c in db.list_chats(search="世界")] == [chat_id]
    assert [c.id for c in db.list_chats(search="untitled")] == [chat_id]


def test_committing_conversation_outside_the_log_is_refused(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="t", config={}, messages=MESSAGES)
    with Session(db.engine) as session:
        chat = session.get(ChatModel, chat_id)
        chat.messages = [*MESSAGES, {"role": "user", "content": "x"}]
        with pytest.raises(RuntimeError):
            session.commit()
    assert len(db.get_chat(chat_id).messages) == 2


def test_a_chat_without_a_log_is_imported_from_its_full_row(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="t", config={}, messages=[])
    db.chat_log.path(chat_id).unlink()
    db.chat_log.forget(chat_id)
    with db.engine.begin() as conn:
        conn.execute(
            text("UPDATE chats SET messages = :m, agent_state = :s WHERE id = :id"),
            {"m": json.dumps(MESSAGES), "s": _state(1), "id": chat_id},
        )
        conn.execute(text("DELETE FROM chat_log_positions"))

    assert len(db.get_chat(chat_id).messages) == 2
    assert db.import_unlogged_chats() == 1
    _assert_slim(db, chat_id)
    chat = db.get_chat(chat_id)
    assert len(chat.messages) == 2
    assert chat.agent_state is not None
    _assert_log_matches(db)
