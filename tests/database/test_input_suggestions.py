from __future__ import annotations


def test_input_suggestion_round_trips_and_is_replaced(temp_db):
    chat_id = temp_db.create_chat("Rain", {})

    temp_db.set_input_suggestion(chat_id, "20:abc", "Now one about snow")
    temp_db.set_input_suggestion(chat_id, "9:def", "Now one about wind")

    saved = temp_db.get_input_suggestion(chat_id)
    assert (saved.reply_key, saved.text) == ("9:def", "Now one about wind")


def test_no_prediction_forgets_the_saved_one(temp_db):
    chat_id = temp_db.create_chat("Rain", {})
    temp_db.set_input_suggestion(chat_id, "20:abc", "Now one about snow")

    temp_db.set_input_suggestion(chat_id, "9:def", None)

    assert temp_db.get_input_suggestion(chat_id) is None


def test_suggestion_is_not_saved_for_a_missing_chat(temp_db):
    temp_db.set_input_suggestion("gone", "20:abc", "Now one about snow")

    assert temp_db.get_input_suggestion("gone") is None


def test_deleting_the_chat_deletes_its_suggestion(temp_db):
    chat_id = temp_db.create_chat("Rain", {})
    temp_db.set_input_suggestion(chat_id, "20:abc", "Now one about snow")

    temp_db.delete_chat(chat_id)

    assert temp_db.get_input_suggestion(chat_id) is None
