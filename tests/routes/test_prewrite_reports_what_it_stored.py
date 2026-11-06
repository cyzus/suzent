"""The turn's licence to skip the user's row is the route's write, not a guess.

A turn cannot tell the row a surface pre-wrote from the identical row an
earlier stopped turn left behind. It trusts the route's word for it -- so a
pre-write that raised, or that the database refused, must not give that word.
"""

from unittest.mock import MagicMock

import pytest

from suzent import database as database_module
from suzent.core import prompt_row


def _stored(chat_id, message, files, client_message_id=None):
    return prompt_row.prewrite_prompt(
        chat_id, message, files, client_message_id=client_message_id
    )[1]


@pytest.fixture
def db(monkeypatch):
    database = MagicMock()
    monkeypatch.setattr(database_module, "get_database", lambda: database)
    return database


def test_a_stored_row_is_reported_as_stored(db):
    db.append_chat_message.return_value = True

    assert _stored("c", "hi", []) is True


def test_a_row_the_database_refused_is_not_reported_as_stored(db):
    # False, not an exception, is how a write against a chat that is gone ends.
    db.append_chat_message.return_value = False

    assert _stored("c", "hi", []) is False


def test_a_write_that_raised_is_not_reported_as_stored(db):
    db.append_chat_message.side_effect = RuntimeError("disk full")

    assert _stored("c", "hi", []) is False


def test_a_failed_write_is_logged_without_the_prompt(db, monkeypatch):
    """A database error carries its statement's bound parameters."""
    written: list[str] = []
    monkeypatch.setattr(
        prompt_row.logger, "debug", lambda msg, *a, **k: written.append(str(msg))
    )

    class _Leaky(RuntimeError):
        def __str__(self):
            return "INSERT INTO messages -- ['the prompt they typed']"

    db.append_chat_message.side_effect = _Leaky()

    stored = _stored("c", "the prompt they typed", [])

    assert stored is False
    assert written and all("the prompt they typed" not in line for line in written)
    assert any("_Leaky" in line for line in written)


def test_nothing_to_write_is_not_a_written_row(db):
    assert _stored("c", "   ", []) is False
    assert db.append_chat_message.call_count == 0


def test_mobile_send_reports_an_existing_client_message_as_duplicate(db):
    db.append_chat_message_once.return_value = "duplicate"

    assert _stored("c", "hi", [], "mobile-1") is None
    db.append_chat_message_once.assert_called_once_with(
        "c", {"role": "user", "content": "hi"}, "mobile-1"
    )
