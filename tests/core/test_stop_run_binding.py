"""A cancellation control belongs to one run, and only that run's stop.

The chat's control changes hands mid-flight: a steer registers the replacement
run's replay before the replacement turn installs its control, so for a moment
the replay says one run and the control still belongs to the turn being
replaced. A stop matched against the replay must not be applied to that control.
"""

from suzent.core import stream_registry
from suzent.core.stream_registry import (
    StreamControl,
    claim_stream_control,
    defer_stop_to_pending_run,
    register_background_stream,
    stop_stream,
)

import pytest


@pytest.fixture(autouse=True)
def clean_registry():
    stream_registry.background_queues.clear()
    stream_registry.stream_controls.clear()
    yield
    stream_registry.background_queues.clear()
    stream_registry.stream_controls.clear()


def test_a_control_takes_a_stop_that_names_its_own_run():
    queue = register_background_stream("chat")
    control = StreamControl()
    claim_stream_control("chat", control)

    assert stop_stream("chat", "bye", expect_run=queue.replay.run_id) is True
    assert control.cancel_event.is_set()
    assert control.reason == "bye"


def test_a_control_refuses_a_stop_that_names_another_run():
    register_background_stream("chat")
    control = StreamControl()
    claim_stream_control("chat", control)
    # The replacement turn's replay is registered; this control is still the
    # one the turn being replaced installed.
    replacement = register_background_stream("chat")

    assert stop_stream("chat", "bye", expect_run=replacement.replay.run_id) is False
    assert not control.cancel_event.is_set()


def test_a_stop_left_for_a_run_is_taken_when_that_run_starts():
    register_background_stream("chat")
    old_control = StreamControl()
    claim_stream_control("chat", old_control)
    replacement = register_background_stream("chat")

    assert defer_stop_to_pending_run("chat", "bye") is True
    assert replacement.replay.stop_requested == "bye"

    new_control = StreamControl()
    claim_stream_control("chat", new_control)

    assert new_control.run_id == replacement.replay.run_id
    assert new_control.cancel_event.is_set()
    assert new_control.reason == "bye"
    # Taken once: the turn after this one starts clean.
    assert replacement.replay.stop_requested is None
    assert not old_control.cancel_event.is_set()


def test_nothing_is_left_for_a_chat_with_no_live_producer():
    queue = register_background_stream("chat")
    queue.put_nowait(None)

    assert defer_stop_to_pending_run("chat", "bye") is False
    assert queue.replay.stop_requested is None


def test_a_stop_that_names_no_run_still_reaches_the_current_control():
    register_background_stream("chat")
    control = StreamControl()
    claim_stream_control("chat", control)

    assert stop_stream("chat", "bye") is True
    assert control.cancel_event.is_set()
