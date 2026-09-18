"""A stop kept for a run that never arrives must not be kept forever.

Nothing obliges the start to come: the chat can be deleted, the request
abandoned. Each entry is read only by a run sharing its chat_id, so one that
never registers is read by nobody.
"""

import pytest

from suzent.core import stream_registry
from suzent.core.stream_registry import (
    MAX_PENDING_CLIENT_STOPS,
    PENDING_CLIENT_STOP_TTL,
    claim_remembered_stop,
    remember_stop_for_unregistered_run,
)


@pytest.fixture(autouse=True)
def clean_registry():
    stream_registry._pending_client_stops.clear()
    yield
    stream_registry._pending_client_stops.clear()


def test_stops_nobody_came_for_are_swept_by_the_next_one(monkeypatch):
    now = stream_registry.time.monotonic()
    monkeypatch.setattr(stream_registry.time, "monotonic", lambda: now)
    for index in range(5):
        remember_stop_for_unregistered_run(f"gone-{index}", "t", "bye")

    monkeypatch.setattr(
        stream_registry.time, "monotonic", lambda: now + PENDING_CLIENT_STOP_TTL + 1
    )
    remember_stop_for_unregistered_run("here", "t", "bye")

    assert list(stream_registry._pending_client_stops) == [("here", "t")]


def test_a_flood_gives_up_its_oldest_rather_than_growing():
    for index in range(MAX_PENDING_CLIENT_STOPS * 2):
        remember_stop_for_unregistered_run(f"chat-{index}", "t", "bye")

    kept = stream_registry._pending_client_stops
    assert len(kept) <= MAX_PENDING_CLIENT_STOPS
    # The newest survive: they are the ones whose start may still be coming.
    assert (f"chat-{MAX_PENDING_CLIENT_STOPS * 2 - 1}", "t") in kept
    assert ("chat-0", "t") not in kept


def test_two_starts_delayed_at_once_each_keep_their_own_stop():
    """Two windows, or a redirect overlapping its own start.

    Each names its own run and each is stopped under that name, so the one that
    registers first must still find the stop its client was told was accepted.
    """
    remember_stop_for_unregistered_run("chat", "token-a", "stop a")
    remember_stop_for_unregistered_run("chat", "token-b", "stop b")

    assert claim_remembered_stop("chat", "token-a") == "stop a"
    assert claim_remembered_stop("chat", "token-b") == "stop b"
    # Each is taken once.
    assert claim_remembered_stop("chat", "token-a") is None
