"""The turn's licence to skip the user's row is the route's write, not a guess.

A turn cannot tell the row /chat/send pre-wrote from the identical row an
earlier stopped turn left behind. It trusts the route's word for it -- so a
pre-write that raised, or that the database refused, must not give that word.
"""

from unittest.mock import MagicMock

import pytest

from suzent.routes import chat_routes


@pytest.fixture
def db(monkeypatch):
    database = MagicMock()
    monkeypatch.setattr(chat_routes, "get_database", lambda: database)
    return database


def test_a_stored_row_is_reported_as_stored(db):
    db.append_chat_message.return_value = True

    assert chat_routes._prewrite_user_display_message("c", "hi", []) is True


def test_a_row_the_database_refused_is_not_reported_as_stored(db):
    # False, not an exception, is how a write against a chat that is gone ends.
    db.append_chat_message.return_value = False

    assert chat_routes._prewrite_user_display_message("c", "hi", []) is False


def test_a_write_that_raised_is_not_reported_as_stored(db):
    db.append_chat_message.side_effect = RuntimeError("disk full")

    assert chat_routes._prewrite_user_display_message("c", "hi", []) is False


def test_a_failed_write_is_logged_without_the_prompt(db, monkeypatch):
    """A database error carries its statement's bound parameters."""
    written: list[str] = []
    monkeypatch.setattr(
        chat_routes.logger, "debug", lambda msg, *a, **k: written.append(str(msg))
    )

    class _Leaky(RuntimeError):
        def __str__(self):
            return "INSERT INTO messages -- ['the prompt they typed']"

    db.append_chat_message.side_effect = _Leaky()

    stored = chat_routes._prewrite_user_display_message(
        "c", "the prompt they typed", []
    )

    assert stored is False
    assert written and all("the prompt they typed" not in line for line in written)
    assert any("_Leaky" in line for line in written)


def test_nothing_to_write_is_not_a_written_row(db):
    assert chat_routes._prewrite_user_display_message("c", "   ", []) is False
    assert db.append_chat_message.call_count == 0
