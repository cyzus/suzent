"""A cron turn's visible record must survive a restart.

Its whole display row is the trigger nested inside the reminder block. That
block is dropped on restart — correctly, since text we cannot authenticate must
not be trusted — so the rebuild alone cannot reconstruct the row. It is taken
from the stored log instead.
"""

from suzent.core.chat_processor import _preserve_display_triggers


def test_restores_a_trigger_row_over_the_placeholder():
    stored = [{"role": "system_triggered", "content": "Cron: daily digest"}]
    rebuilt = [{"role": "user", "content": "[system trigger: Cron: daily digest]"}]

    out = _preserve_display_triggers(rebuilt, stored)

    assert out[0]["role"] == "system_triggered"
    assert out[0]["content"] == "Cron: daily digest"


def test_leaves_a_genuine_user_message_alone():
    """The row at this index is someone's actual message, not a placeholder."""
    stored = [{"role": "system_triggered", "content": "Cron: daily digest"}]
    rebuilt = [{"role": "user", "content": "please refactor the parser"}]

    out = _preserve_display_triggers(rebuilt, stored)

    assert out[0]["role"] == "user"
    assert out[0]["content"] == "please refactor the parser"


def test_leaves_an_already_correct_trigger_row_alone():
    stored = [{"role": "system_triggered", "content": "Cron: daily digest"}]
    rebuilt = [{"role": "system_triggered", "content": "Cron: daily digest"}]

    assert _preserve_display_triggers(rebuilt, stored) == rebuilt


def test_preserves_other_fields_on_the_restored_row():
    stored = [{"role": "system_triggered", "content": "Cron: digest"}]
    rebuilt = [
        {"role": "user", "content": "[system trigger: Cron: digest]", "timestamp": 42}
    ]

    out = _preserve_display_triggers(rebuilt, stored)

    assert out[0]["timestamp"] == 42


def test_tolerates_diverged_histories():
    stored = [{"role": "system_triggered", "content": "Cron"}, {"role": "user"}]
    rebuilt = [{"role": "user", "content": "[system trigger: Cron]"}]

    out = _preserve_display_triggers(rebuilt, stored)

    assert len(out) == 1
    assert out[0]["role"] == "system_triggered"


def test_no_stored_log_is_a_noop():
    rebuilt = [{"role": "user", "content": "hi"}]

    assert _preserve_display_triggers(rebuilt, None) == rebuilt
    assert _preserve_display_triggers(rebuilt, []) == rebuilt


def test_ignores_non_dict_rows():
    out = _preserve_display_triggers(["junk"], [{"role": "system_triggered"}])

    assert out == ["junk"]
