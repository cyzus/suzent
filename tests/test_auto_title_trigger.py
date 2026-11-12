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


def test_auto_title_is_skipped_when_the_chat_opts_out() -> None:
    chat = SimpleNamespace(
        turn_count=0, title="[run] Fix the tests", config={"auto_title": False}
    )

    assert should_generate_auto_title(chat) is False


def test_auto_title_ignores_a_chat_config_without_the_setting() -> None:
    chat = SimpleNamespace(turn_count=0, title="New Chat", config={"model": "x"})

    assert should_generate_auto_title(chat) is True
