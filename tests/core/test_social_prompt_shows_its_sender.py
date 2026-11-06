"""A chat-app message is in the desktop transcript before its turn, with its sender.

The social path wrote the prompt only from inside the turn, wrapped in the
platform envelope the model reads, so the desktop showed `[Telegram Alice id:42]`
as if the user had typed it, and nothing said which app or person it came from.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from suzent import database as database_module
from suzent.core import prompt_row


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    database = MagicMock()
    database.append_chat_message.return_value = True
    monkeypatch.setattr(database_module, "get_database", lambda: database)
    return database


def test_the_row_carries_the_sender_and_not_the_envelope(db: MagicMock) -> None:
    prompt_row.prewrite_prompt(
        "social-telegram-42",
        "what's on today?",
        metadata={"source": "social", "sender": "Alice", "channel": "Telegram"},
    )

    db.append_chat_message.assert_called_once_with(
        "social-telegram-42",
        {
            "role": "user",
            "content": "what's on today?",
            "metadata": {"source": "social", "sender": "Alice", "channel": "Telegram"},
        },
    )


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("Alice", "Alice"),
        ("  Alice  ", "Alice"),
        ("evil\x1b[31m", "Unknown sender"),
        ("x" * 101, "Unknown sender"),
        ("", "Unknown sender"),
        (None, "Unknown sender"),
    ],
)
def test_only_a_printable_name_is_shown(name: object, shown: str) -> None:
    assert prompt_row.display_name(name, "Unknown sender") == shown
