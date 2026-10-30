from __future__ import annotations


def test_memory_recall_is_replaced_each_turn(temp_db):
    chat_id = temp_db.create_chat("Rain", {})

    temp_db.set_memory_recall(chat_id, [{"id": "m1", "content": "Likes rain"}])
    temp_db.set_memory_recall(chat_id, [])

    assert temp_db.get_memory_recall(chat_id).items == []


def test_recall_is_not_saved_for_a_missing_chat(temp_db):
    temp_db.set_memory_recall("gone", [{"id": "m1", "content": "Likes rain"}])

    assert temp_db.get_memory_recall("gone") is None


def test_deleting_the_chat_deletes_its_recall(temp_db):
    chat_id = temp_db.create_chat("Rain", {})
    temp_db.set_memory_recall(chat_id, [{"id": "m1", "content": "Likes rain"}])

    temp_db.delete_chat(chat_id)

    assert temp_db.get_memory_recall(chat_id) is None
