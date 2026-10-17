import json
import random
import threading

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlmodel import Session

from suzent.core.agent_serializer import serialize_state
from suzent.database import ChatDatabase, ChatModel
from suzent.database.chat_log import (
    ChatEventLog,
    ChatLogError,
    apply_splice,
    project_chat,
    project_state,
    splice_diff,
    state_bytes,
)


def _state(turns: int) -> bytes:
    messages = []
    for index in range(turns):
        messages.append(ModelRequest(parts=[UserPromptPart(content=f"q{index}")]))
        messages.append(ModelResponse(parts=[TextPart(content=f"a{index}")]))
    return serialize_state(messages, model_id="test:model", tool_names=["bash"])


def _events(db: ChatDatabase, chat_id: str) -> list[dict]:
    return list(db.chat_log.events(chat_id))


def _assert_log_matches(db: ChatDatabase) -> None:
    assert db.chat_log_differences(db.chat_log) == {}


def test_splice_round_trips_random_lists() -> None:
    rng = random.Random(7)
    for _ in range(500):
        old = [rng.randint(0, 4) for _ in range(rng.randint(0, 8))]
        new = [rng.randint(0, 4) for _ in range(rng.randint(0, 8))]
        splice = splice_diff(old, new)
        if splice is None:
            assert old == new
        else:
            assert apply_splice(old, splice) == new


def test_appending_one_item_is_a_one_item_splice() -> None:
    assert splice_diff([1, 2], [1, 2, 3]) == {"start": 2, "delete": 0, "insert": [3]}


def test_out_of_range_splice_is_rejected() -> None:
    with pytest.raises(ChatLogError):
        apply_splice([1], {"start": 1, "delete": 1, "insert": []})


@pytest.mark.parametrize("raw", [None, b"", b"\x80not json", _state(2)])
def test_agent_state_bytes_round_trip(raw) -> None:
    assert state_bytes(project_state(raw)) == raw


def test_every_chat_write_keeps_the_log_equal_to_sqlite(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(
        title="Log", config={"model": "m"}, messages=[{"role": "user", "content": "hi"}]
    )
    _assert_log_matches(db)

    db.append_chat_message(chat_id, {"role": "assistant", "content": "hello"})
    db.append_chat_message_once(
        chat_id, {"role": "user", "content": "again"}, client_message_id="c1"
    )
    db.merge_chat_config(chat_id, {"permission_mode": "auto"})
    db.update_chat(chat_id, title="Renamed", agent_state=_state(1), pinned=True)
    _assert_log_matches(db)

    revision = db.commit_snapshot_state(chat_id, agent_state=_state(2))
    finalized = db.finalize_state_if_revision_matches(
        chat_id,
        expected_revision=revision,
        agent_state=_state(2),
        messages=db.get_chat(chat_id).messages
        + [{"role": "assistant", "content": "x"}],
    )
    assert finalized
    db.mark_chat_read(chat_id)
    _assert_log_matches(db)

    db.rewrite_chat_messages(
        chat_id, [{"role": "user", "content": "hi"}], agent_state=None
    )
    project_id = db.create_project(name="Other", slug="other")
    db.link_chat_to_project(chat_id, project_id)
    fork_id = db.clone_chat_to_point(chat_id, up_to_message_index=1)
    _assert_log_matches(db)

    db.delete_chat(fork_id)
    _assert_log_matches(db)
    assert not db.chat_log.path(fork_id).exists()
    assert list((db.chat_log.root / ".trash").glob(f"{fork_id}.*.jsonl"))


def test_folding_the_log_rebuilds_the_row(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Rebuild", config={})
    for turn in range(1, 4):
        db.append_chat_message(chat_id, {"role": "user", "content": f"q{turn}"})
        db.update_chat(chat_id, agent_state=_state(turn))

    logged, seq = db.chat_log.fold(chat_id)
    chat = db.get_chat(chat_id)
    assert seq == len(_events(db, chat_id))
    assert logged == project_chat(chat)
    assert state_bytes(logged["state"]) == chat.agent_state


def test_log_grows_with_the_turn_not_the_conversation(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Growth", config={})
    for turn in range(10):
        db.append_chat_message(chat_id, {"role": "user", "content": f"m{turn}"})

    splices = [e for e in _events(db, chat_id) if e["type"] == "messages.splice"]
    assert len(splices) == 10
    assert all(len(e["data"]["insert"]) == 1 for e in splices)


def test_streaming_drafts_stay_out_of_the_log(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Draft", config={})
    before = len(_events(db, chat_id))
    draft = {"role": "assistant", "content": "par", "_streaming_draft": True}
    db.update_chat(chat_id, messages=[draft], reindex=False)

    assert len(_events(db, chat_id)) == before
    db.merge_chat_config(chat_id, {"k": 1})
    _assert_log_matches(db)
    assert all(
        "_streaming_draft" not in json.dumps(e["data"]) for e in _events(db, chat_id)
    )


def test_verify_reports_a_write_that_bypassed_the_log(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Raw", config={})
    with Session(db.engine) as session:
        chat = session.get(ChatModel, chat_id)
        chat.title = "Changed behind the log"
        session.add(chat)
        session.commit()

    assert db.chat_log_differences(db.chat_log) == {chat_id: ["title"]}
    db.record_chat_change(chat_id)
    _assert_log_matches(db)


def test_torn_final_line_is_ignored_then_repaired(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Torn", config={})
    path = db.chat_log.path(chat_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"v": 1, "seq": 99, "type": "meta.set"')

    assert db.chat_log.fold(chat_id)[1] == 1
    db.chat_log.forget(chat_id)
    db.append_chat_message(chat_id, {"role": "user", "content": "after crash"})

    seqs = [e["seq"] for e in _events(db, chat_id)]
    assert seqs == list(range(1, len(seqs) + 1))
    _assert_log_matches(db)


def test_backfill_logs_chats_written_before_the_log_existed(temp_db) -> None:
    db = temp_db
    chat_log, db.chat_log = db.chat_log, None
    chat_id = db.create_chat(title="Old", config={})
    db.chat_log = chat_log

    assert db.chat_log_differences(chat_log) == {chat_id: ["<missing log>"]}
    assert db.sync_chat_logs() == 1
    assert _events(db, chat_id)[0]["type"] == "chat.imported"
    _assert_log_matches(db)


def test_unsafe_chat_ids_are_refused(tmp_path) -> None:
    chat_log = ChatEventLog(tmp_path)
    for chat_id in ("../escape", "a/b", ""):
        with pytest.raises(ChatLogError):
            chat_log.path(chat_id)


def test_sqlite_mode_writes_no_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SUZENT_CHAT_STORE", "sqlite")
    db = ChatDatabase(str(tmp_path / "chats.db"))
    db.create_chat(title="No log", config={})

    assert db.chat_log is None
    assert not (tmp_path / "chats").exists()
    db.engine.dispose()


def test_concurrent_writers_leave_the_log_equal_to_sqlite(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Race", config={})

    def write(prefix: str) -> None:
        for index in range(15):
            db.merge_chat_config(chat_id, {f"{prefix}{index}": index})

    threads = [threading.Thread(target=write, args=(p,)) for p in "ab"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    _assert_log_matches(db)
