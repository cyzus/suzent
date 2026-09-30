from suzent.core.retry import (
    load_retry_checkpoint,
    record_retry_checkpoint_revision,
    save_retry_checkpoint,
)
from suzent.database import ChatDatabase


def test_retry_checkpoint_stays_bound_to_its_own_turn(
    temp_db: ChatDatabase, monkeypatch
):
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    chat_id = temp_db.create_chat("Retry revisions", {}, [])
    checkpoint_id = save_retry_checkpoint(chat_id, None, [], "Question", [], {})
    assert checkpoint_id is not None
    assert "_retry_revision" not in load_retry_checkpoint(chat_id).config_snapshot

    revision = temp_db.commit_snapshot_state(chat_id, b"human-state")
    record_retry_checkpoint_revision(chat_id, checkpoint_id, revision)
    checkpoint = load_retry_checkpoint(chat_id)
    assert checkpoint.config_snapshot["_retry_revision"] == revision

    before = temp_db.get_chat(chat_id).messages
    heartbeat_revision = temp_db.commit_snapshot_state(
        chat_id, b"hidden-heartbeat-state"
    )
    assert temp_db.get_chat(chat_id).messages == before
    assert (
        heartbeat_revision
        != load_retry_checkpoint(chat_id).config_snapshot["_retry_revision"]
    )

    next_id = save_retry_checkpoint(
        chat_id, b"hidden-heartbeat-state", [], "Next", [], {}
    )
    assert next_id != checkpoint_id
    record_retry_checkpoint_revision(chat_id, checkpoint_id, revision)
    assert "_retry_revision" not in load_retry_checkpoint(chat_id).config_snapshot
    record_retry_checkpoint_revision(chat_id, next_id, heartbeat_revision + 1)
    assert (
        load_retry_checkpoint(chat_id).config_snapshot["_retry_revision"]
        == heartbeat_revision + 1
    )


def test_replay_rejects_revision_changed_after_validation(temp_db, monkeypatch):
    from suzent.core.retry import apply_retry_checkpoint

    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    chat_id = temp_db.create_chat("Replay race", {}, [])
    token = save_retry_checkpoint(chat_id, b"before", [], "Question", [], {})
    revision = temp_db.commit_snapshot_state(chat_id, b"completed")
    record_retry_checkpoint_revision(chat_id, token, revision)
    temp_db.commit_snapshot_state(chat_id, b"heartbeat")

    assert apply_retry_checkpoint(chat_id, expected_revision=revision) is None
    assert temp_db.get_chat(chat_id).agent_state == b"heartbeat"


def test_replay_invalidates_pending_finalizer(temp_db, monkeypatch):
    from suzent.core.retry import apply_retry_checkpoint

    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    chat_id = temp_db.create_chat("Finalize race", {}, [])
    token = save_retry_checkpoint(chat_id, b"before", [], "Question", [], {})
    revision = temp_db.commit_snapshot_state(chat_id, b"completed")
    record_retry_checkpoint_revision(chat_id, token, revision)

    assert apply_retry_checkpoint(chat_id, expected_revision=revision) is not None
    assert not temp_db.finalize_state_if_revision_matches(
        chat_id, revision, b"late-completed", [{"role": "assistant", "content": "old"}]
    )
    assert temp_db.get_chat(chat_id).agent_state == b"before"
    assert temp_db.get_chat(chat_id).messages == []
    assert apply_retry_checkpoint(chat_id, expected_revision=revision) is None
