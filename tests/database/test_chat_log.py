import json
import random
import threading

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlalchemy import text
from sqlmodel import Session

from suzent.core.agent_serializer import serialize_state
from suzent.database import ChatDatabase, ChatModel
from suzent.database.chat_log import (
    MEDIA_THRESHOLD,
    ChatEventLog,
    ChatLogError,
    apply_splice,
    project_chat,
    project_state,
    splice_diff,
    state_bytes,
)


class CrashBeforeCommit(BaseException):
    """Stands in for the process dying between the log append and the commit."""


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


def _reopen(db: ChatDatabase) -> ChatDatabase:
    db.engine.dispose()
    return ChatDatabase(str(db.db_path))


def _crash_on_commit(db: ChatDatabase, monkeypatch) -> None:
    """Make the next chat write die after its log append, with no clean-up."""

    def crash(self) -> None:
        raise CrashBeforeCommit

    monkeypatch.setattr(Session, "commit", crash)
    monkeypatch.setattr(db.chat_log, "undo", lambda pending: None)


def _snapshot(db: ChatDatabase) -> dict[str, dict]:
    return {
        chat_id: project_chat(db.get_chat(chat_id)) for chat_id in db.all_chat_ids()
    }


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
    assert {**logged, "checkpoint": None} == {**project_chat(chat), "checkpoint": None}
    assert state_bytes(logged["state"]) == chat.agent_state


def test_log_grows_with_the_turn_not_the_conversation(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Growth", config={})
    for turn in range(10):
        db.append_chat_message(chat_id, {"role": "user", "content": f"m{turn}"})

    appends = [e for e in _events(db, chat_id) if e["type"] == "message.append"]
    assert [e["data"]["content"] for e in appends] == [f"m{t}" for t in range(10)]


def test_a_log_reads_one_message_per_line(temp_db) -> None:
    db = temp_db
    messages = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    chat_id = db.create_chat(
        title="Lines", config={}, messages=messages, agent_state=_state(1)
    )

    events = _events(db, chat_id)
    assert [e["type"] for e in events] == [
        "chat.created",
        "message.append",
        "message.append",
        "history.append",
        "history.append",
    ]
    assert events[0]["data"]["messages"] == []
    assert [e["data"] for e in events[1:3]] == messages

    db.rewrite_chat_messages(chat_id, messages[:1])
    assert _events(db, chat_id)[-1]["type"] == "messages.splice"
    _assert_log_matches(db)


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


def test_a_write_that_bypassed_the_log_is_recorded_by_the_next_one(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Raw", config={})
    with Session(db.engine) as session:
        chat = session.get(ChatModel, chat_id)
        chat.title = "Changed behind the log"
        session.add(chat)
        session.commit()

    assert db.chat_log_differences(db.chat_log) == {chat_id: ["title"]}
    db.merge_chat_config(chat_id, {"k": 1})
    _assert_log_matches(db)


def test_a_failed_commit_takes_its_events_back_out(temp_db, monkeypatch) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Rollback", config={})
    size = db.chat_log.path(chat_id).stat().st_size

    def fail(self) -> None:
        raise RuntimeError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail)
        with pytest.raises(RuntimeError):
            db.append_chat_message(chat_id, {"role": "user", "content": "lost"})

    assert db.chat_log.path(chat_id).stat().st_size == size
    assert db.get_chat(chat_id).messages == []
    db.append_chat_message(chat_id, {"role": "user", "content": "kept"})
    _assert_log_matches(db)


def test_events_a_crash_kept_out_of_sqlite_are_replayed_on_start(
    temp_db, monkeypatch
) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Crash", config={})
    with monkeypatch.context() as patch:
        _crash_on_commit(db, patch)
        with pytest.raises(CrashBeforeCommit):
            db.append_chat_message(chat_id, {"role": "user", "content": "logged"})
    assert db.get_chat(chat_id).messages == []

    reopened = _reopen(db)
    assert reopened.get_chat(chat_id).messages == [
        {"role": "user", "content": "logged"}
    ]
    assert reopened.fts_match_chat_ids("logged") == [chat_id]
    _assert_log_matches(reopened)
    reopened.engine.dispose()


def test_a_deletion_a_crash_kept_out_of_sqlite_finishes_on_start(
    temp_db, monkeypatch
) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Doomed", config={})
    with monkeypatch.context() as patch:
        _crash_on_commit(db, patch)
        with pytest.raises(CrashBeforeCommit):
            db.delete_chat(chat_id)
    assert db.get_chat(chat_id) is not None

    reopened = _reopen(db)
    assert reopened.get_chat(chat_id) is None
    assert not reopened.chat_log.path(chat_id).exists()
    assert list((reopened.chat_log.root / ".trash").glob("*.jsonl"))
    reopened.engine.dispose()


def test_deleting_chats_db_rebuilds_every_chat_from_the_logs(temp_db) -> None:
    db = temp_db
    first = db.create_chat(
        title="First",
        config={"model": "m"},
        messages=[{"role": "user", "content": "needle in the first chat"}],
        agent_state=_state(1),
    )
    db.update_chat(first, pinned=True, context_usage={"tokens": 12})
    revision = db.commit_snapshot_state(first, agent_state=_state(2))
    db.finalize_state_if_revision_matches(
        first,
        revision,
        _state(2),
        db.get_chat(first).messages + [{"role": "assistant", "content": "done"}],
    )
    fork = db.clone_chat_to_point(first, up_to_message_index=1)
    db.merge_chat_config(fork, {"forked_from_chat_id": first})
    gone = db.create_chat(title="Gone", config={})
    db.delete_chat(gone)
    before = _snapshot(db)

    db.engine.dispose()
    db.db_path.unlink()
    rebuilt = ChatDatabase(str(db.db_path))

    assert _snapshot(rebuilt).keys() == before.keys()
    for chat_id, projection in _snapshot(rebuilt).items():
        expected = before[chat_id]
        # Projects live only in chats.db, so the rebuilt chats join the new
        # default project.
        assert {**projection, "project_id": None} == {**expected, "project_id": None}
        assert projection["project_id"] == rebuilt.get_project_by_slug("default").id
    assert sorted(rebuilt.fts_match_chat_ids("needle")) == sorted([first, fork])
    assert [chat.id for chat in rebuilt.list_chats(pinned=True)] == [first]
    _assert_log_matches(rebuilt)
    rebuilt.engine.dispose()


def test_a_hand_edited_log_is_replayed_on_start(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Before", config={})
    seq = _events(db, chat_id)[-1]["seq"]
    edit = {"v": 1, "seq": seq + 1, "type": "meta.set", "data": {"title": "After"}}
    with db.chat_log.path(chat_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(edit) + "\n")

    reopened = _reopen(db)
    assert reopened.get_chat(chat_id).title == "After"
    reopened.engine.dispose()


def test_a_log_from_before_archiving_matches_its_row(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Legacy", config={})
    path = db.chat_log.path(chat_id)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    for event in events:
        event["data"].pop("archived", None)
    path.write_text("".join(json.dumps(event) + "\n" for event in events))

    assert db.chat_log_differences(db.chat_log) == {}
    reopened = _reopen(db)
    assert reopened.get_chat(chat_id).archived is False
    reopened.engine.dispose()


def test_rebuild_index_rewrites_rows_that_drifted(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Logged", config={})
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE chats SET title = 'Drifted'"))

    assert db.reconcile_chat_logs() == 0
    assert db.reconcile_chat_logs(rebuild=True) == 1
    assert db.get_chat(chat_id).title == "Logged"


def test_an_empty_log_leaves_the_row_alone(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Kept", config={})
    db.chat_log.path(chat_id).write_text("")

    reopened = _reopen(db)
    assert reopened.get_chat(chat_id).title == "Kept"
    reopened.merge_chat_config(chat_id, {"k": 1})
    assert _events(reopened, chat_id)[0]["type"] == "chat.imported"
    reopened.engine.dispose()


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


@pytest.mark.parametrize(
    "line",
    [
        "[]",
        '{"v": 1, "seq": 2, "data": {}}',
        '{"v": 1, "seq": 2, "type": "messages.splice", "data": {"start": 0}}',
    ],
)
def test_an_unreadable_log_is_reported_then_set_aside(temp_db, line) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Bad", config={})
    with db.chat_log.path(chat_id).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    db.chat_log.forget(chat_id)

    report = db.chat_log_differences(db.chat_log)
    assert list(report) == [chat_id]
    assert report[chat_id][0].startswith("<unreadable log")

    db.merge_chat_config(chat_id, {"k": 1})
    assert list((db.chat_log.root / ".corrupt").glob("*.jsonl"))
    assert _events(db, chat_id)[0]["type"] == "chat.imported"
    _assert_log_matches(db)


def test_chats_without_a_log_are_imported(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Old", config={})
    db.chat_log.path(chat_id).unlink()
    db.chat_log.forget(chat_id)

    assert db.chat_log_differences(db.chat_log) == {chat_id: ["<missing log>"]}
    assert db.import_unlogged_chats() == 1
    assert _events(db, chat_id)[0]["type"] == "chat.imported"
    _assert_log_matches(db)


def test_any_chat_id_maps_to_a_file_inside_the_log_directory(tmp_path) -> None:
    chat_log = ChatEventLog(tmp_path)
    chat_ids = ["suzent:peer-1", "a/b", "../escape", "..", "social-tg-@ü"]
    for chat_id in chat_ids:
        path = chat_log.path(chat_id)
        assert path.parent == tmp_path
        path.write_text("")
    assert chat_log.chat_ids() == sorted(chat_ids)
    with pytest.raises(ChatLogError):
        chat_log.path("")


def test_peer_chats_are_logged(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Peer", config={}, chat_id="suzent:peer-1")
    db.append_chat_message(chat_id, {"role": "user", "content": "hi"})

    assert _events(db, chat_id)[0]["type"] == "chat.created"
    _assert_log_matches(db)


def test_separate_database_instances_refresh_cached_log_before_writing(temp_db) -> None:
    first = temp_db
    chat_id = first.create_chat(title="Shared", config={})
    second = ChatDatabase(str(first.db_path))
    try:
        second.chat_log.logged(chat_id)
        first.append_chat_message(chat_id, {"role": "user", "content": "one"})
        second.append_chat_message(chat_id, {"role": "assistant", "content": "two"})
        first.append_chat_message(chat_id, {"role": "user", "content": "three"})

        events = _events(first, chat_id)
        assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
        _assert_log_matches(first)
    finally:
        second.engine.dispose()


def test_large_strings_are_stored_once_outside_the_log(temp_db) -> None:
    db = temp_db
    image = "data:image/png;base64," + "A" * MEDIA_THRESHOLD
    chat_id = db.create_chat(title="Image", config={})
    db.append_chat_message(chat_id, {"role": "user", "content": image})
    db.append_chat_message(chat_id, {"role": "user", "content": image})

    assert db.chat_log.path(chat_id).stat().st_size < MEDIA_THRESHOLD
    assert len(list(db.chat_log.media_root.iterdir())) == 1
    logged, _ = db.chat_log.fold(chat_id)
    assert [m["content"] for m in logged["messages"]] == [image, image]

    db.engine.dispose()
    db.db_path.unlink()
    rebuilt = ChatDatabase(str(db.db_path))
    assert rebuilt.get_chat(chat_id).messages[0]["content"] == image
    rebuilt.engine.dispose()


def test_a_checkpoint_of_the_stored_chat_points_into_the_log(
    temp_db, monkeypatch
) -> None:
    from suzent.core.retry import apply_retry_checkpoint, save_retry_checkpoint

    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    db = temp_db
    history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    chat_id = db.create_chat(
        title="Retry", config={}, messages=history, agent_state=_state(1)
    )
    chat = db.get_chat(chat_id)
    size = db.chat_log.path(chat_id).stat().st_size

    assert save_retry_checkpoint(
        chat_id, chat.agent_state, chat.messages, "next", [], {}
    )
    checkpoint_event = _events(db, chat_id)[-1]
    assert checkpoint_event["type"] == "checkpoint.set"
    assert checkpoint_event["data"]["before"] == {"seq": checkpoint_event["seq"] - 1}
    assert db.chat_log.path(chat_id).stat().st_size - size < 1000

    db.append_chat_message(chat_id, {"role": "user", "content": "next"})
    db.update_chat(chat_id, agent_state=_state(2))
    restored = apply_retry_checkpoint(chat_id)

    assert restored["user_message"] == "next"
    assert db.get_chat(chat_id).messages == history
    assert db.get_chat(chat_id).agent_state == chat.agent_state
    _assert_log_matches(db)


def test_checkpoints_survive_a_rebuild(temp_db, monkeypatch) -> None:
    from suzent.core.retry import load_retry_checkpoint, save_retry_checkpoint

    db = temp_db
    chat_id = db.create_chat(title="Retry", config={})
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    checkpoint_id = save_retry_checkpoint(chat_id, b"other", [], "question", [], {})
    db.record_turn_file_changes(chat_id, [{"path": "/a.txt"}])

    db.engine.dispose()
    db.db_path.unlink()
    rebuilt = ChatDatabase(str(db.db_path))
    monkeypatch.setattr("suzent.database.get_database", lambda: rebuilt)
    checkpoint = load_retry_checkpoint(chat_id)

    assert checkpoint.id == checkpoint_id
    assert checkpoint.agent_state_before == b"other"
    assert checkpoint.file_snapshot == [{"path": "/a.txt"}]
    rebuilt.engine.dispose()


def test_legacy_retry_checkpoints_move_into_the_log(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(
        title="Legacy", config={}, messages=[{"role": "user", "content": "q"}]
    )
    with db.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE retry_checkpoints (chat_id VARCHAR PRIMARY KEY, "
                "agent_state_before BLOB, messages_before JSON, user_message "
                "VARCHAR, user_files JSON, config_snapshot JSON, has_file_snapshot "
                "BOOLEAN, file_snapshot JSON, created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO retry_checkpoints VALUES (:id, NULL, '[]', 'q', '[]', "
                """'{"_retry_checkpoint_id": "old", "_retry_revision": 3}', 0, """
                "'[]', '2026-01-01')"
            ),
            {"id": chat_id},
        )

    db.import_unlogged_chats()

    checkpoint = db.get_retry_checkpoint(chat_id)
    assert checkpoint.id == "old"
    assert checkpoint.config_snapshot["_retry_revision"] == 3
    assert checkpoint.messages_before == []
    with db.engine.connect() as connection:
        tables = connection.execute(
            text("SELECT name FROM sqlite_master WHERE name = 'retry_checkpoints'")
        ).all()
    assert tables == []


def test_old_trash_is_purged(tmp_path) -> None:
    chat_log = ChatEventLog(tmp_path)
    chat_log.path("old").write_text("")
    chat_log.retire("old")

    assert chat_log.purge_trash(max_age_days=1) == 0
    assert chat_log.purge_trash(max_age_days=0) == 1


def test_concurrent_writers_leave_the_log_equal_to_sqlite(temp_db) -> None:
    db = temp_db
    chat_id = db.create_chat(title="Race", config={})
    chat = db.get_chat(chat_id)
    db.save_retry_checkpoint(
        chat_id,
        checkpoint_id="c",
        agent_state_before=chat.agent_state,
        messages_before=chat.messages,
        user_message="q",
        user_files=[],
        config_snapshot={},
    )
    errors: list[BaseException] = []

    def write(prefix: str) -> None:
        try:
            for index in range(15):
                if prefix == "c":
                    # A write whose session changes no row.
                    db.update_retry_checkpoint(chat_id, "c", {"user_message": index})
                else:
                    db.merge_chat_config(chat_id, {f"{prefix}{index}": index})
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(p,)) for p in "abc"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    _assert_log_matches(db)
    assert db.get_retry_checkpoint(chat_id).user_message == 14


def test_chats_show_prints_the_logged_conversation(temp_db, monkeypatch) -> None:
    from typer.testing import CliRunner

    from suzent.cli.chats import chats_app

    db = temp_db
    chat_id = db.create_chat(
        title="Shown", config={}, messages=[{"role": "user", "content": "hello"}]
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)

    result = CliRunner().invoke(chats_app, ["show", chat_id])
    assert result.exit_code == 0
    assert "Shown" in result.output
    assert "[user]\nhello" in result.output
    assert CliRunner().invoke(chats_app, ["show", "missing"]).exit_code == 1
