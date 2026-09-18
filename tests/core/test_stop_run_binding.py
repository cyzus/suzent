"""A cancellation control belongs to one run, and only that run's stop.

The chat's control changes hands mid-flight: a steer registers the replacement
run's replay before the replacement turn installs its control, so for a moment
the replay says one run and the control still belongs to the turn being
replaced. A stop matched against the replay must not be applied to that control.
"""

from suzent.core import stream_registry
from suzent.core.stream_registry import (
    StreamControl,
    bind_producer_replay,
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
    bind_producer_replay(None)
    yield
    stream_registry.background_queues.clear()
    stream_registry.stream_controls.clear()


def test_a_control_takes_a_stop_that_names_its_own_run():
    queue = register_background_stream("chat")
    bind_producer_replay(queue.replay)
    control = StreamControl()
    claim_stream_control("chat", control)

    assert stop_stream("chat", "bye", expect_run=queue.replay.run_id) is True
    assert control.cancel_event.is_set()
    assert control.reason == "bye"


def test_a_control_refuses_a_stop_that_names_another_run():
    original = register_background_stream("chat")
    bind_producer_replay(original.replay)
    control = StreamControl()
    claim_stream_control("chat", control)
    # The replacement turn's replay is registered; this control is still the
    # one the turn being replaced installed.
    replacement = register_background_stream("chat")

    assert stop_stream("chat", "bye", expect_run=replacement.replay.run_id) is False
    assert not control.cancel_event.is_set()


def test_a_stop_left_for_a_run_is_taken_when_that_run_starts():
    original = register_background_stream("chat")
    bind_producer_replay(original.replay)
    old_control = StreamControl()
    claim_stream_control("chat", old_control)
    replacement = register_background_stream("chat")

    assert defer_stop_to_pending_run("chat", "bye") is True
    assert replacement.replay.stop_requested == "bye"

    bind_producer_replay(replacement.replay)
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
    queue = register_background_stream("chat")
    bind_producer_replay(queue.replay)
    control = StreamControl()
    claim_stream_control("chat", control)

    assert stop_stream("chat", "bye") is True
    assert control.cancel_event.is_set()


def test_a_turn_that_started_before_the_steer_keeps_its_own_run():
    """The steer's replay is registered while the first turn is still starting.

    Binding to whatever replay the chat holds would label this control with the
    replacement's run -- and let it swallow the stop left for that run, so the
    stop would cancel this turn and the redirected one would run on.
    """
    original = register_background_stream("chat")
    bind_producer_replay(original.replay)
    replacement = register_background_stream("chat")
    replacement.replay.stop_requested = "bye"

    control = StreamControl()
    claim_stream_control("chat", control)

    assert control.run_id == original.replay.run_id
    assert not control.cancel_event.is_set()
    assert replacement.replay.stop_requested == "bye"


def test_a_producer_that_declared_no_run_leaves_the_control_unnamed():
    """Heartbeats, sub-agents and social turns own no replay.

    An unnamed control refuses any stop that names a run, which is the safe
    direction: there is no replay a stop could have been matched against.
    """
    queue = register_background_stream("chat")
    bind_producer_replay(None)
    control = StreamControl()
    claim_stream_control("chat", control)

    assert control.run_id is None
    assert stop_stream("chat", "bye", expect_run=queue.replay.run_id) is False
    assert stop_stream("chat", "bye") is True


@pytest.mark.asyncio
async def test_a_background_turn_declares_the_run_it_produces():
    """Heartbeat, cron and sub-agent turns are watchable, so they are stoppable.

    Their queue is a real, observable one: the frontend attaches to it and
    stops it by the run id the replay hands out. A producer that never says
    which run it is producing leaves its control unnamed, and the stop is
    refused and then deferred onto a run that is already past taking it.
    """
    from unittest.mock import AsyncMock, patch

    from suzent.core.chat_processor import ChatProcessor
    from suzent.core.stream_registry import current_run_replay

    seen: list[object] = []

    async def _turn(*args, **kwargs):
        seen.append(current_run_replay.get())
        return "done"

    with patch.object(ChatProcessor, "process_turn_text", AsyncMock(side_effect=_turn)):
        await ChatProcessor().process_background_turn(
            chat_id="chat", user_id="u", message_content="hi"
        )

    queue = stream_registry.background_queues["chat"]
    assert seen == [queue.replay]
    # And the declaration does not outlive the turn.
    assert current_run_replay.get() is None
