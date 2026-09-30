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
