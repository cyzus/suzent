from types import SimpleNamespace

from suzent.core.auto_title import should_generate_auto_title


def test_auto_title_runs_on_first_turn() -> None:
    chat = SimpleNamespace(title="New Chat", turn_count=0)

    assert should_generate_auto_title(chat) is True


def test_auto_title_retries_placeholder_title_after_first_turn() -> None:
    chat = SimpleNamespace(title="New Chat", turn_count=2)

    assert should_generate_auto_title(chat) is True


def test_auto_title_does_not_overwrite_custom_title_after_first_turn() -> None:
    chat = SimpleNamespace(title="Project Planning", turn_count=2)

    assert should_generate_auto_title(chat) is False
