"""The sidebar message summary stays consistent with chat.messages across rollback
paths, and a one-time repair fixes summaries that drifted before the fix.
"""

import pytest

from suzent.database.chats import (
    SUMMARY_LAST_MESSAGE_KEY,
    SUMMARY_VISIBLE_COUNT_KEY,
)


@pytest.fixture
def db(temp_db):
    return temp_db


def _assistant(text):
    return {
        "role": "assistant",
        "content": text,
        "parts": [{"type": "text", "text": text}],
    }


def _count(db, chat_id):
    return (db.get_chat(chat_id).config or {}).get(SUMMARY_VISIBLE_COUNT_KEY)


def test_rewrite_chat_messages_refreshes_summary(db):
    cid = db.create_chat("C", {}, [{"role": "user", "content": "q"}])
    assert _count(db, cid) == 0
    db.rewrite_chat_messages(
        cid,
        [{"role": "user", "content": "q"}, _assistant("an answer")],
    )
    assert _count(db, cid) == 1
    assert (db.get_chat(cid).config or {})[SUMMARY_LAST_MESSAGE_KEY] == "an answer"


def test_rewrite_chat_messages_applies_turn_count_delta(db):
    cid = db.create_chat("C", {}, [{"role": "user", "content": "q"}, _assistant("a")])
    before = db.get_chat(cid).turn_count or 0
    db.rewrite_chat_messages(
        cid, [{"role": "user", "content": "q"}], turn_count_delta=-1
    )
    assert (db.get_chat(cid).turn_count or 0) == max(0, before - 1)
    # Truncating to just the user message drops the visible (assistant) count to 0.
    assert _count(db, cid) == 0


def test_list_chats_count_consistent_after_rollback(db):
    # Simulate a heartbeat/retry rollback shrinking the message list and confirm the
    # sidebar list reports the refreshed count, not the pre-rollback one.
    cid = db.create_chat(
        "C", {}, [{"role": "user", "content": "q"}, _assistant("temp reply")]
    )
    assert _count(db, cid) == 1
    db.rewrite_chat_messages(cid, [{"role": "user", "content": "q"}])
    summary = next(s for s in db.list_chats() if s.id == cid)
    assert summary.messageCount == 0


def test_one_time_summary_repair_fixes_stale_count(db):
    # Force a stale summary the way the old rollback paths did: messages have an
    # assistant reply, but the cached count says 0.
    cid = db.create_chat(
        "C", {}, [{"role": "user", "content": "q"}, _assistant("real reply")]
    )
    db.merge_chat_config(cid, {SUMMARY_VISIBLE_COUNT_KEY: 0})
    assert _count(db, cid) == 0

    # Clear the one-time flag so the repair runs again, then run it.
    from suzent.core.user_config import UserConfigStore

    UserConfigStore().save_config_blob(db._SUMMARY_REPAIR_FLAG, "")
    db._repair_stale_chat_summaries()

    assert _count(db, cid) == 1


def test_summary_repair_is_one_shot(db):
    cid = db.create_chat("C", {}, [{"role": "user", "content": "q"}, _assistant("a")])
    # First run already happened during db init; corrupt the count and re-run without
    # clearing the flag — repair must be a no-op the second time.
    db.merge_chat_config(cid, {SUMMARY_VISIBLE_COUNT_KEY: 99})
    db._repair_stale_chat_summaries()
    assert _count(db, cid) == 99
